"""
Analytics Engine Module
Tracks quiz performance, generates reports, and provides insights
"""

import json
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import statistics
import logging

import numpy as np

logger = logging.getLogger(__name__)

class AnalyticsEngine:
    """
    Analytics engine for tracking learning progress and generating insights
    """
    
    def __init__(self):
        self.sessions = defaultdict(list)  # user_id -> list of sessions
        self.quiz_results = {}  # quiz_id -> results
        self.aggregate_stats = defaultdict(dict)
        self.question_analytics = defaultdict(dict)  # question_id -> analytics
        
    def track_quiz_generation(self, user_id: str, metadata: Dict) -> None:
        """Track when a quiz is generated"""
        
        event = {
            'type': 'quiz_generated',
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat(),
            'metadata': metadata
        }
        
        self.sessions[user_id].append(event)
        logger.info(f"Tracked quiz generation for user {user_id}")
    
    def track_answer(self, user_id: str, question_id: str, 
                    answer_data: Dict) -> None:
        """Track individual answer submission"""
        
        # Update question analytics
        if question_id not in self.question_analytics:
            self.question_analytics[question_id] = {
                'attempts': 0,
                'correct': 0,
                'average_time': 0,
                'difficulty_rating': [],
                'common_mistakes': defaultdict(int)
            }
        
        analytics = self.question_analytics[question_id]
        analytics['attempts'] += 1
        
        if answer_data.get('is_correct'):
            analytics['correct'] += 1
        else:
            # Track common wrong answers
            wrong_answer = answer_data.get('user_answer')
            if wrong_answer:
                analytics['common_mistakes'][wrong_answer] += 1
        
        # Update average time
        if 'time_taken' in answer_data:
            current_avg = analytics['average_time']
            n = analytics['attempts']
            analytics['average_time'] = (
                (current_avg * (n - 1) + answer_data['time_taken']) / n
            )
        
        # Track user session
        event = {
            'type': 'answer_submitted',
            'user_id': user_id,
            'question_id': question_id,
            'timestamp': datetime.utcnow().isoformat(),
            'data': answer_data
        }
        
        self.sessions[user_id].append(event)
    
    def generate_report(self, quiz_id: str, answers: List[Dict], 
                       time_taken: int) -> Dict:
        """
        Generate comprehensive quiz report
        """
        
        report = {
            'quiz_id': quiz_id,
            'timestamp': datetime.utcnow().isoformat(),
            'total_questions': len(answers),
            'time_taken': time_taken,
            'answers': answers
        }
        
        # Calculate basic metrics
        correct_answers = sum(1 for a in answers if a.get('is_correct'))
        report['correct_answers'] = correct_answers
        report['incorrect_answers'] = len(answers) - correct_answers
        report['overall_score'] = correct_answers / len(answers) if answers else 0
        report['percentage'] = report['overall_score'] * 100
        
        # Calculate time metrics
        if time_taken and len(answers):
            report['average_time'] = time_taken / len(answers)
            report['time_per_correct'] = (
                time_taken / correct_answers if correct_answers else 0
            )
        
        # Analyze by topic
        topic_performance = defaultdict(lambda: {'correct': 0, 'total': 0})
        for answer in answers:
            topic = answer.get('topic', 'General')
            topic_performance[topic]['total'] += 1
            if answer.get('is_correct'):
                topic_performance[topic]['correct'] += 1
        
        report['topic_scores'] = {
            topic: data['correct'] / data['total'] 
            for topic, data in topic_performance.items()
        }
        
        # Analyze by Bloom's taxonomy
        bloom_performance = defaultdict(lambda: {'correct': 0, 'total': 0})
        for answer in answers:
            bloom_level = answer.get('bloom_level', 'understand')
            bloom_performance[bloom_level]['total'] += 1
            if answer.get('is_correct'):
                bloom_performance[bloom_level]['correct'] += 1
        
        report['bloom_scores'] = {
            level: data['correct'] / data['total'] if data['total'] > 0 else 0
            for level, data in bloom_performance.items()
        }
        
        # Analyze by question type
        type_performance = defaultdict(lambda: {'correct': 0, 'total': 0})
        for answer in answers:
            q_type = answer.get('question_type', 'unknown')
            type_performance[q_type]['total'] += 1
            if answer.get('is_correct'):
                type_performance[q_type]['correct'] += 1
        
        report['type_scores'] = {
            q_type: data['correct'] / data['total'] if data['total'] > 0 else 0
            for q_type, data in type_performance.items()
        }
        
        # Identify patterns
        report['patterns'] = self._identify_patterns(answers)
        
        # Generate insights
        report['insights'] = self._generate_insights(report)
        
        # Calculate streak
        report['longest_correct_streak'] = self._calculate_streak(answers, True)
        report['longest_incorrect_streak'] = self._calculate_streak(answers, False)
        
        # Performance trend
        report['performance_trend'] = self._calculate_trend(answers)
        
        # Store result
        self.quiz_results[quiz_id] = report
        
        return report
    
    def _identify_patterns(self, answers: List[Dict]) -> Dict:
        """Identify patterns in quiz responses"""
        
        patterns = {
            'rushing': False,
            'fatigue': False,
            'guessing': False,
            'consistent': False,
            'improving': False,
            'declining': False
        }
        
        if not answers:
            return patterns
        
        # Check for rushing (very fast responses)
        times = [a.get('time_taken', 0) for a in answers if 'time_taken' in a]
        if times and statistics.mean(times) < 10:  # Less than 10 seconds average
            patterns['rushing'] = True
        
        # Check for fatigue (declining performance over time)
        if len(answers) >= 5:
            first_half = answers[:len(answers)//2]
            second_half = answers[len(answers)//2:]
            
            first_accuracy = sum(1 for a in first_half if a.get('is_correct')) / len(first_half)
            second_accuracy = sum(1 for a in second_half if a.get('is_correct')) / len(second_half)
            
            if second_accuracy < first_accuracy - 0.2:
                patterns['fatigue'] = True
                patterns['declining'] = True
            elif second_accuracy > first_accuracy + 0.2:
                patterns['improving'] = True
        
        # Check for guessing (multiple choice with ~25% accuracy)
        mc_answers = [a for a in answers if a.get('question_type') == 'multiple_choice']
        if mc_answers:
            mc_accuracy = sum(1 for a in mc_answers if a.get('is_correct')) / len(mc_answers)
            if 0.2 <= mc_accuracy <= 0.3:
                patterns['guessing'] = True
        
        # Check for consistency
        if len(answers) >= 3:
            correctness = [a.get('is_correct', False) for a in answers]
            changes = sum(1 for i in range(1, len(correctness)) 
                         if correctness[i] != correctness[i-1])
            if changes <= len(correctness) * 0.3:
                patterns['consistent'] = True
        
        return patterns
    
    def _generate_insights(self, report: Dict) -> List[str]:
        """Generate actionable insights from the report"""
        
        insights = []
        
        # Overall performance insights
        score = report['overall_score']
        if score >= 0.9:
            insights.append("Excellent performance! You've mastered this material.")
        elif score >= 0.7:
            insights.append("Good understanding. Focus on the topics you missed.")
        elif score >= 0.5:
            insights.append("Developing understanding. More practice recommended.")
        else:
            insights.append("Significant gaps identified. Consider reviewing the material.")
        
        # Topic-specific insights
        weak_topics = [
            topic for topic, score in report['topic_scores'].items() 
            if score < 0.6
        ]
        if weak_topics:
            insights.append(f"Focus on: {', '.join(weak_topics[:3])}")
        
        strong_topics = [
            topic for topic, score in report['topic_scores'].items() 
            if score >= 0.8
        ]
        if strong_topics:
            insights.append(f"Strong in: {', '.join(strong_topics[:3])}")
        
        # Bloom's taxonomy insights
        bloom_scores = report.get('bloom_scores', {})
        if bloom_scores.get('remember', 1) < 0.6:
            insights.append("Strengthen factual knowledge and memorization.")
        if bloom_scores.get('understand', 1) < 0.6:
            insights.append("Work on comprehension and explanation skills.")
        if bloom_scores.get('apply', 1) < 0.6:
            insights.append("Practice applying concepts to new situations.")
        if bloom_scores.get('analyze', 1) < 0.6:
            insights.append("Develop analytical and critical thinking skills.")
        
        # Pattern-based insights
        patterns = report.get('patterns', {})
        if patterns.get('rushing'):
            insights.append("Take more time to read questions carefully.")
        if patterns.get('fatigue'):
            insights.append("Consider taking breaks during longer quizzes.")
        if patterns.get('guessing'):
            insights.append("Review the material before attempting quizzes.")
        if patterns.get('improving'):
            insights.append("Great progress! You're warming up nicely.")
        
        # Time-based insights
        avg_time = report.get('average_time', 0)
        if avg_time > 120:
            insights.append("You're being thorough, but try to improve speed.")
        elif avg_time < 20:
            insights.append("Consider spending more time on each question.")
        
        return insights
    
    def _calculate_streak(self, answers: List[Dict], correct: bool) -> int:
        """Calculate longest streak of correct or incorrect answers"""
        
        if not answers:
            return 0
        
        max_streak = 0
        current_streak = 0
        
        for answer in answers:
            if answer.get('is_correct', False) == correct:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        
        return max_streak
    
    def _calculate_trend(self, answers: List[Dict]) -> str:
        """Calculate performance trend over the quiz"""
        
        if len(answers) < 3:
            return "insufficient_data"
        
        # Calculate rolling accuracy
        window_size = min(3, len(answers) // 3)
        accuracies = []
        
        for i in range(len(answers) - window_size + 1):
            window = answers[i:i + window_size]
            accuracy = sum(1 for a in window if a.get('is_correct')) / window_size
            accuracies.append(accuracy)
        
        if not accuracies:
            return "stable"
        
        # Fit trend line
        x = np.arange(len(accuracies))
        slope = np.polyfit(x, accuracies, 1)[0]
        
        if slope > 0.1:
            return "improving"
        elif slope < -0.1:
            return "declining"
        else:
            return "stable"
    
    def get_user_history(self, user_id: str) -> Dict:
        """Get user's learning history"""
        
        if user_id not in self.sessions:
            return {'user_id': user_id, 'recent_sessions': []}
        
        user_sessions = self.sessions[user_id]
        
        # Group events into sessions
        sessions = []
        current_session = []
        last_timestamp = None
        
        for event in user_sessions:
            timestamp = datetime.fromisoformat(event['timestamp'])
            
            # New session if more than 1 hour gap
            if last_timestamp and (timestamp - last_timestamp).seconds > 3600:
                if current_session:
                    sessions.append(self._process_session(current_session))
                current_session = []
            
            current_session.append(event)
            last_timestamp = timestamp
        
        # Add final session
        if current_session:
            sessions.append(self._process_session(current_session))
        
        # Return last 10 sessions
        return {
            'user_id': user_id,
            'recent_sessions': sessions[-10:]
        }
    
    def _process_session(self, events: List[Dict]) -> Dict:
        """Process session events into summary"""
        
        session = {
            'start_time': events[0]['timestamp'],
            'end_time': events[-1]['timestamp'],
            'questions_answered': 0,
            'correct_answers': 0,
            'topic_performance': {},
            'bloom_performance': {},
            'accuracy': 0
        }
        
        for event in events:
            if event['type'] == 'answer_submitted':
                session['questions_answered'] += 1
                
                if event['data'].get('is_correct'):
                    session['correct_answers'] += 1
                
                # Track topic performance
                topic = event['data'].get('topic', 'General')
                if topic not in session['topic_performance']:
                    session['topic_performance'][topic] = {'correct': 0, 'total': 0}
                
                session['topic_performance'][topic]['total'] += 1
                if event['data'].get('is_correct'):
                    session['topic_performance'][topic]['correct'] += 1
                
                # Track Bloom performance
                bloom = event['data'].get('bloom_level', 'understand')
                if bloom not in session['bloom_performance']:
                    session['bloom_performance'][bloom] = {'correct': 0, 'total': 0}
                
                session['bloom_performance'][bloom]['total'] += 1
                if event['data'].get('is_correct'):
                    session['bloom_performance'][bloom]['correct'] += 1
        
        # Calculate accuracy scores
        session['accuracy'] = (
            session['correct_answers'] / session['questions_answered'] 
            if session['questions_answered'] > 0 else 0
        )
        
        # Convert counts to percentages
        for topic, data in session['topic_performance'].items():
            session['topic_performance'][topic] = (
                data['correct'] / data['total'] if data['total'] > 0 else 0
            )
        
        for bloom, data in session['bloom_performance'].items():
            session['bloom_performance'][bloom] = (
                data['correct'] / data['total'] if data['total'] > 0 else 0
            )
        
        return session
    
    def get_user_analytics(self, user_id: str) -> Dict:
        """Get comprehensive analytics for a user"""
        
        history = self.get_user_history(user_id)
        sessions = history['recent_sessions']
        
        if not sessions:
            return {
                'user_id': user_id,
                'total_sessions': 0,
                'message': 'No data available yet'
            }
        
        # Aggregate statistics
        total_questions = sum(s['questions_answered'] for s in sessions)
        total_correct = sum(s['correct_answers'] for s in sessions)
        
        # Topic mastery
        topic_totals = defaultdict(lambda: {'correct': 0, 'total': 0})
        for session in sessions:
            for topic, score in session.get('topic_performance', {}).items():
                topic_totals[topic]['total'] += 1
                topic_totals[topic]['correct'] += score
        
        topic_mastery = {
            topic: data['correct'] / data['total'] if data['total'] > 0 else 0
            for topic, data in topic_totals.items()
        }
        
        # Learning curve (accuracy over time)
        learning_curve = [
            {
                'date': s['start_time'],
                'accuracy': s['accuracy']
            }
            for s in sessions
        ]
        
        # Time analysis
        total_time = 0
        for session in sessions:
            start = datetime.fromisoformat(session['start_time'])
            end = datetime.fromisoformat(session['end_time'])
            total_time += (end - start).seconds
        
        # Calculate improvement
        if len(sessions) >= 2:
            initial_accuracy = sessions[0]['accuracy']
            recent_accuracy = statistics.mean(s['accuracy'] for s in sessions[-3:])
            improvement = recent_accuracy - initial_accuracy
        else:
            improvement = 0
        
        return {
            'user_id': user_id,
            'total_sessions': len(sessions),
            'total_questions_attempted': total_questions,
            'total_correct': total_correct,
            'overall_accuracy': total_correct / total_questions if total_questions > 0 else 0,
            'topic_mastery': topic_mastery,
            'learning_curve': learning_curve,
            'total_study_time': total_time,
            'average_session_time': total_time / len(sessions) if sessions else 0,
            'improvement': improvement,
            'last_activity': sessions[-1]['end_time'] if sessions else None,
            'strengths': sorted(
                topic_mastery.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:3],
            'weaknesses': sorted(
                topic_mastery.items(), 
                key=lambda x: x[1]
            )[:3]
        }
    
    def export_data(self, user_id: str) -> Dict:
        """Export user data for download or backup"""
        
        return {
            'user_id': user_id,
            'sessions': self.sessions[user_id],
            'analytics': self.get_user_analytics(user_id),
            'export_date': datetime.utcnow().isoformat()
        }
    
    def import_data(self, data: Dict) -> None:
        """Import user data from backup"""
        
        user_id = data['user_id']
        if 'sessions' in data:
            self.sessions[user_id] = data['sessions']
        
        logger.info(f"Imported data for user {user_id}")
