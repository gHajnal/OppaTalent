#!/usr/bin/env python3
"""
OppaTalent - Main Application
AI-powered adaptive quiz generation for educational content
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import hashlib
import redis
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
import jwt

from quiz_generator import QuizGenerator
from document_processor import DocumentProcessor
from analytics_engine import AnalyticsEngine
from adaptive_engine import AdaptiveEngine
from canvas_integration import CanvasLTIProvider

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, static_folder='frontend', static_url_path='')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'temp_uploads'

# Initialize CORS with specific origins for production
CORS(app, origins=['http://localhost:5000', 'https://canvas.instructure.com'])

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"]
)

# Initialize Redis for caching (optional, falls back to in-memory if not available)
try:
    cache = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    cache.ping()
    logger.info("Redis cache connected")
except:
    cache = None
    logger.warning("Redis not available, using in-memory cache")
    from collections import OrderedDict
    cache = OrderedDict()  # Simple LRU cache fallback

# Initialize components
doc_processor = DocumentProcessor()
quiz_gen = QuizGenerator(api_key=os.environ.get('OPENAI_API_KEY'))
analytics = AnalyticsEngine()
adaptive_engine = AdaptiveEngine()
canvas_lti = CanvasLTIProvider(
    consumer_key=os.environ.get('CANVAS_CONSUMER_KEY'),
    consumer_secret=os.environ.get('CANVAS_CONSUMER_SECRET')
)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Cache decorator
def cached(expiration=3600):
    """Cache decorator with configurable expiration"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{f.__name__}:{str(args)}:{str(kwargs)}"
            cache_key = hashlib.md5(cache_key.encode()).hexdigest()
            
            # Try to get from cache
            if cache:
                if isinstance(cache, dict):
                    result = cache.get(cache_key)
                else:
                    result = cache.get(cache_key)
                    
                if result:
                    logger.info(f"Cache hit for {f.__name__}")
                    return json.loads(result) if isinstance(result, str) else result
            
            # Call function and cache result
            result = f(*args, **kwargs)
            
            if cache:
                if isinstance(cache, dict):
                    cache[cache_key] = result
                    # Simple LRU: keep only last 100 items
                    if len(cache) > 100:
                        cache.pop(next(iter(cache)))
                else:
                    cache.setex(cache_key, expiration, json.dumps(result))
            
            return result
        return wrapper
    return decorator

# Authentication decorator (simplified for demo)
def require_auth(f):
    """Simple JWT authentication decorator"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not token and app.config.get('ENV') == 'development':
            # Allow no auth in development
            return f(*args, **kwargs)
        
        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user = payload
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid authentication token'}), 401
        
        return f(*args, **kwargs)
    return wrapper

# Routes
@app.route('/')
def index():
    """Serve the main application"""
    return send_from_directory('frontend', 'index.html')

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0',
        'ai_service': quiz_gen.check_connection()
    })

@app.route('/api/upload', methods=['POST'])
@limiter.limit("10 per minute")
def upload_document():
    """
    Process uploaded document and extract content
    Supports: PDF, TXT, DOCX, MD
    """
    try:
        if 'document' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['document']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file type
        allowed_extensions = {'pdf', 'txt', 'docx', 'md', 'doc'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'error': f'Unsupported file type. Allowed: {", ".join(allowed_extensions)}'}), 400
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Process document
        logger.info(f"Processing document: {filename}")
        content = doc_processor.extract_text(filepath)
        
        # Clean up temp file
        os.remove(filepath)
        
        # Analyze content for metadata
        analysis = quiz_gen.analyze_content(content)
        
        # Check for PII and sanitize
        sanitized_content = doc_processor.remove_pii(content)
        
        return jsonify({
            'success': True,
            'content': sanitized_content,
            'metadata': {
                'word_count': len(content.split()),
                'estimated_reading_time': len(content.split()) // 200,  # Average reading speed
                'topics': analysis.get('topics', []),
                'difficulty_level': analysis.get('difficulty', 'intermediate'),
                'suggested_questions': analysis.get('possible_questions', 10),
                'pii_removed': content != sanitized_content
            }
        })
        
    except Exception as e:
        logger.error(f"Error processing upload: {str(e)}")
        return jsonify({'error': f'Failed to process document: {str(e)}'}), 500

@app.route('/api/generate-quiz', methods=['POST'])
@limiter.limit("5 per minute")
@cached(expiration=7200)  # Cache for 2 hours
def generate_quiz():
    """
    Generate adaptive quiz questions using AI
    Implements Bloom's Taxonomy and adaptive difficulty
    """
    try:
        data = request.json
        content = data.get('content')
        
        if not content:
            return jsonify({'error': 'No content provided'}), 400
        
        # Quiz configuration
        config = {
            'num_questions': data.get('num_questions', 10),
            'question_types': data.get('question_types', ['multiple_choice', 'true_false', 'short_answer']),
            'difficulty_distribution': data.get('difficulty_distribution', {
                'remember': 0.2,
                'understand': 0.3,
                'apply': 0.3,
                'analyze': 0.2
            }),
            'learning_mode': data.get('learning_mode', 'adaptive'),
            'include_hints': data.get('include_hints', True),
            'include_explanations': data.get('include_explanations', True)
        }
        
        # Get user's learning history if available
        user_id = request.headers.get('X-User-ID', 'anonymous')
        learning_history = analytics.get_user_history(user_id)
        
        # Adapt difficulty based on history
        if learning_history and config['learning_mode'] == 'adaptive':
            config = adaptive_engine.adjust_config(config, learning_history)
        
        # Generate quiz
        logger.info(f"Generating quiz with config: {config}")
        quiz = quiz_gen.generate_quiz(content, config)
        
        # Add metadata for tracking
        quiz['metadata'] = {
            'generated_at': datetime.utcnow().isoformat(),
            'config': config,
            'estimated_time': config['num_questions'] * 1.5,  # 1.5 minutes per question
            'ai_model': 'gpt-4',
            'token_usage': quiz_gen.last_token_usage,
            'estimated_cost': quiz_gen.calculate_cost(quiz_gen.last_token_usage)
        }
        
        # Track generation for analytics
        analytics.track_quiz_generation(user_id, quiz['metadata'])
        
        return jsonify(quiz)
        
    except Exception as e:
        logger.error(f"Error generating quiz: {str(e)}")
        return jsonify({'error': f'Failed to generate quiz: {str(e)}'}), 500

@app.route('/api/validate-answer', methods=['POST'])
@limiter.limit("20 per minute")
def validate_answer():
    """
    AI-powered answer validation with semantic understanding
    Provides detailed feedback and partial credit
    """
    try:
        data = request.json
        question = data.get('question')
        correct_answer = data.get('correct_answer')
        user_answer = data.get('user_answer')
        question_type = data.get('question_type', 'short_answer')
        
        if not all([question, correct_answer, user_answer]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Quick validation for objective questions
        if question_type in ['multiple_choice', 'true_false']:
            is_correct = user_answer.lower().strip() == correct_answer.lower().strip()
            return jsonify({
                'is_correct': is_correct,
                'score': 1.0 if is_correct else 0.0,
                'feedback': 'Correct!' if is_correct else f'The correct answer is: {correct_answer}'
            })
        
        # AI validation for subjective answers
        validation = quiz_gen.validate_answer(
            question=question,
            correct_answer=correct_answer,
            user_answer=user_answer,
            rubric=data.get('rubric', None)
        )
        
        # Add learning recommendations
        if not validation['is_correct']:
            validation['recommendations'] = adaptive_engine.get_recommendations(
                question_topic=data.get('topic'),
                performance=validation['score']
            )
        
        return jsonify(validation)
        
    except Exception as e:
        logger.error(f"Error validating answer: {str(e)}")
        return jsonify({'error': f'Failed to validate answer: {str(e)}'}), 500

@app.route('/api/submit-quiz', methods=['POST'])
@require_auth
def submit_quiz():
    """
    Submit completed quiz for grading and analytics
    Generates detailed performance report
    """
    try:
        data = request.json
        quiz_id = data.get('quiz_id')
        answers = data.get('answers')
        time_taken = data.get('time_taken')
        
        # Calculate scores and generate report
        report = analytics.generate_report(
            quiz_id=quiz_id,
            answers=answers,
            time_taken=time_taken
        )
        
        # Update adaptive engine with performance
        user_id = request.headers.get('X-User-ID', 'anonymous')
        adaptive_engine.update_user_model(user_id, report)
        
        # Generate study recommendations
        recommendations = adaptive_engine.generate_study_plan(
            user_id=user_id,
            performance=report
        )
        
        report['recommendations'] = recommendations
        
        # If Canvas LTI, send grade back
        if 'lis_outcome_service_url' in request.headers:
            canvas_lti.send_grade(
                score=report['overall_score'],
                outcome_url=request.headers['lis_outcome_service_url']
            )
        
        return jsonify(report)
        
    except Exception as e:
        logger.error(f"Error submitting quiz: {str(e)}")
        return jsonify({'error': f'Failed to submit quiz: {str(e)}'}), 500

@app.route('/api/analytics/user/<user_id>')
@require_auth
def get_user_analytics(user_id):
    """Get detailed analytics for a specific user"""
    try:
        analytics_data = analytics.get_user_analytics(user_id)
        return jsonify(analytics_data)
    except Exception as e:
        logger.error(f"Error fetching analytics: {str(e)}")
        return jsonify({'error': f'Failed to fetch analytics: {str(e)}'}), 500

@app.route('/api/export-quiz', methods=['POST'])
@require_auth
def export_quiz():
    """
    Export quiz in various formats (JSON, QTI, Canvas)
    """
    try:
        data = request.json
        quiz = data.get('quiz')
        format_type = data.get('format', 'json')
        
        if format_type == 'qti':
            # QTI format for LMS import
            exported = quiz_gen.export_to_qti(quiz)
        elif format_type == 'canvas':
            # Canvas-specific format
            exported = canvas_lti.format_quiz(quiz)
        else:
            # Default JSON format
            exported = quiz
        
        return jsonify({
            'format': format_type,
            'data': exported,
            'filename': f"quiz_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format_type}"
        })
        
    except Exception as e:
        logger.error(f"Error exporting quiz: {str(e)}")
        return jsonify({'error': f'Failed to export quiz: {str(e)}'}), 500

@app.route('/api/study-guide', methods=['POST'])
@limiter.limit("3 per minute")
def generate_study_guide():
    """
    Generate AI-powered study guide based on quiz performance
    """
    try:
        data = request.json
        quiz_results = data.get('quiz_results')
        content = data.get('original_content')
        
        study_guide = quiz_gen.generate_study_guide(
            content=content,
            weak_areas=quiz_results.get('weak_topics', []),
            performance=quiz_results.get('overall_score', 0)
        )
        
        return jsonify(study_guide)
        
    except Exception as e:
        logger.error(f"Error generating study guide: {str(e)}")
        return jsonify({'error': f'Failed to generate study guide: {str(e)}'}), 500

@app.route('/lti/launch', methods=['POST'])
def lti_launch():
    """Handle LTI launch from Canvas"""
    try:
        if canvas_lti.validate_request(request):
            # Store LTI parameters in session
            session_data = canvas_lti.extract_launch_data(request)
            
            # Generate token for session
            token = jwt.encode(
                {'lti_data': session_data, 'exp': datetime.utcnow() + timedelta(hours=2)},
                app.config['SECRET_KEY'],
                algorithm='HS256'
            )
            
            # Redirect to app with token
            return f"""
            <html>
                <body>
                    <script>
                        window.location.href = '/?token={token}';
                    </script>
                </body>
            </html>
            """
        else:
            return "Invalid LTI launch", 403
            
    except Exception as e:
        logger.error(f"LTI launch error: {str(e)}")
        return "LTI launch failed", 500

@app.route('/api/ai-usage')
def get_ai_usage():
    """Get current AI usage statistics"""
    return jsonify({
        'total_tokens': quiz_gen.total_tokens_used,
        'total_cost': quiz_gen.total_cost,
        'requests_today': quiz_gen.requests_today,
        'average_response_time': quiz_gen.avg_response_time
    })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': f'Rate limit exceeded: {e.description}'}), 429

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('ENV', 'development') == 'development'
    
    logger.info(f"Starting OppaTalent on port {port}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"AI Service: {'Connected' if quiz_gen.check_connection() else 'Not connected'}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
