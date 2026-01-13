"""
Adaptive Learning Engine
Implements personalized learning algorithms based on student performance
Uses spaced repetition and difficulty adjustment
"""

import json
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class PerformanceLevel(Enum):
    STRUGGLING = "struggling"
    DEVELOPING = "developing"
    PROFICIENT = "proficient"
    ADVANCED = "advanced"

@dataclass
class LearnerProfile:
    """Profile of a learner's strengths and weaknesses"""
    user_id: str
    total_questions_answered: int = 0
    correct_answers: int = 0
    topics_mastery: Dict[str, float] = None  # topic -> mastery level (0-1)
    bloom_performance: Dict[str, float] = None  # bloom level -> performance
    average_time_per_question: float = 0
    learning_velocity: float = 0  # Rate of improvement
    last_session: Optional[datetime] = None
    strengths: List[str] = None
    weaknesses: List[str] = None
    preferred_question_types: List[str] = None
    
    def __post_init__(self):
        if self.topics_mastery is None:
            self.topics_mastery = {}
        if self.bloom_performance is None:
            self.bloom_performance = {}
        if self.strengths is None:
            self.strengths = []
        if self.weaknesses is None:
            self.weaknesses = []
        if self.preferred_question_types is None:
            self.preferred_question_types = []

class AdaptiveEngine:
    """
    Adaptive learning engine that personalizes quiz difficulty
    and content based on learner performance
    """
    
    def __init__(self):
        self.learner_profiles = {}
        self.topic_difficulty = defaultdict(float)  # Global topic difficulty
        self.question_bank = defaultdict(list)  # Store questions for reuse
        
        # Spaced repetition intervals (in days)
        self.repetition_intervals = [1, 3, 7, 14, 30, 90]
        
        # Performance thresholds
        self.thresholds = {
            PerformanceLevel.STRUGGLING: 0.4,
            PerformanceLevel.DEVELOPING: 0.6,
            PerformanceLevel.PROFICIENT: 0.8,
            PerformanceLevel.ADVANCED: 0.95
        }
    
    def get_or_create_profile(self, user_id: str) -> LearnerProfile:
        """Get existing profile or create new one"""
        if user_id not in self.learner_profiles:
            self.learner_profiles[user_id] = LearnerProfile(user_id=user_id)
        return self.learner_profiles[user_id]
    
    def adjust_config(self, config: Dict, learning_history: Dict) -> Dict:
        """
        Adjust quiz configuration based on learner's history
        Implements adaptive difficulty and content selection
        """
        user_id = learning_history.get('user_id', 'anonymous')
        profile = self.get_or_create_profile(user_id)
        
        # Update profile from history
        self._update_profile_from_history(profile, learning_history)
        
        # Determine current performance level
        performance_level = self._calculate_performance_level(profile)
        
        # Adjust difficulty distribution based on performance
        config = self._adjust_difficulty_distribution(config, performance_level, profile)
        
        # Select topics based on weaknesses and spaced repetition
        config = self._select_adaptive_topics(config, profile)
        
        # Adjust number of questions based on fatigue and engagement
        config = self._adjust_question_count(config, profile)
        
        # Select question types based on preferences
        config = self._select_question_types(config, profile)
        
        logger.info(f"Adapted config for user {user_id}: {performance_level.value}")
        
        return config
    
    def _update_profile_from_history(self, profile: LearnerProfile, 
                                    history: Dict) -> None:
        """Update learner profile with recent performance"""
        
        if 'recent_sessions' in history:
            for session in history['recent_sessions']:
                profile.total_questions_answered += session.get('questions_answered', 0)
                profile.correct_answers += session.get('correct_answers', 0)
                
                # Update topic mastery
                for topic, performance in session.get('topic_performance', {}).items():
                    if topic not in profile.topics_mastery:
                        profile.topics_mastery[topic] = performance
                    else:
                        # Exponential moving average
                        profile.topics_mastery[topic] = (
                            0.7 * profile.topics_mastery[topic] + 0.3 * performance
                        )
                
                # Update Bloom's taxonomy performance
                for bloom_level, performance in session.get('bloom_performance', {}).items():
                    if bloom_level not in profile.bloom_performance:
                        profile.bloom_performance[bloom_level] = performance
                    else:
                        profile.bloom_performance[bloom_level] = (
                            0.7 * profile.bloom_performance[bloom_level] + 0.3 * performance
                        )
        
        # Calculate learning velocity (improvement rate)
        if profile.total_questions_answered > 0:
            profile.learning_velocity = self._calculate_learning_velocity(history)
        
        # Identify strengths and weaknesses
        self._identify_strengths_weaknesses(profile)
        
        profile.last_session = datetime.now()
    
    def _calculate_performance_level(self, profile: LearnerProfile) -> PerformanceLevel:
        """Determine learner's overall performance level"""
        
        if profile.total_questions_answered == 0:
            return PerformanceLevel.DEVELOPING
        
        accuracy = profile.correct_answers / profile.total_questions_answered
        
        for level in [PerformanceLevel.ADVANCED, PerformanceLevel.PROFICIENT, 
                     PerformanceLevel.DEVELOPING]:
            if accuracy >= self.thresholds[level]:
                return level
        
        return PerformanceLevel.STRUGGLING
    
    def _adjust_difficulty_distribution(self, config: Dict, 
                                       level: PerformanceLevel,
                                       profile: LearnerProfile) -> Dict:
        """Adjust Bloom's taxonomy distribution based on performance"""
        
        distributions = {
            PerformanceLevel.STRUGGLING: {
                'remember': 0.4,
                'understand': 0.4,
                'apply': 0.15,
                'analyze': 0.05
            },
            PerformanceLevel.DEVELOPING: {
                'remember': 0.25,
                'understand': 0.35,
                'apply': 0.25,
                'analyze': 0.15
            },
            PerformanceLevel.PROFICIENT: {
                'remember': 0.15,
                'understand': 0.25,
                'apply': 0.35,
                'analyze': 0.25
            },
            PerformanceLevel.ADVANCED: {
                'remember': 0.05,
                'understand': 0.15,
                'apply': 0.30,
                'analyze': 0.30,
                'evaluate': 0.10,
                'create': 0.10
            }
        }
        
        config['difficulty_distribution'] = distributions[level]
        
        # Fine-tune based on specific Bloom level performance
        if profile.bloom_performance:
            for bloom_level, performance in profile.bloom_performance.items():
                if performance < 0.5 and bloom_level in config['difficulty_distribution']:
                    # Increase practice for weak areas
                    config['difficulty_distribution'][bloom_level] *= 1.2
        
        # Normalize distribution
        total = sum(config['difficulty_distribution'].values())
        config['difficulty_distribution'] = {
            k: v/total for k, v in config['difficulty_distribution'].items()
        }
        
        return config
    
    def _select_adaptive_topics(self, config: Dict, 
                               profile: LearnerProfile) -> Dict:
        """Select topics based on weaknesses and spaced repetition"""
        
        topics_to_review = []
        
        # Add weak topics
        for topic, mastery in profile.topics_mastery.items():
            if mastery < 0.6:  # Below mastery threshold
                topics_to_review.append({
                    'topic': topic,
                    'priority': 1 - mastery,  # Higher priority for weaker topics
                    'reason': 'weakness'
                })
        
        # Add topics due for spaced repetition
        if profile.last_session:
            days_since_last = (datetime.now() - profile.last_session).days
            
            for topic, mastery in profile.topics_mastery.items():
                # Calculate optimal review interval based on mastery
                interval_index = min(int(mastery * len(self.repetition_intervals)), 
                                   len(self.repetition_intervals) - 1)
                review_interval = self.repetition_intervals[interval_index]
                
                if days_since_last >= review_interval:
                    topics_to_review.append({
                        'topic': topic,
                        'priority': 0.5,
                        'reason': 'spaced_repetition'
                    })
        
        # Sort by priority and select top topics
        topics_to_review.sort(key=lambda x: x['priority'], reverse=True)
        config['focus_topics'] = [t['topic'] for t in topics_to_review[:5]]
        
        return config
    
    def _adjust_question_count(self, config: Dict, 
                              profile: LearnerProfile) -> Dict:
        """Adjust number of questions based on engagement and fatigue"""
        
        base_questions = config.get('num_questions', 10)
        
        # Adjust based on average time per question
        if profile.average_time_per_question > 0:
            if profile.average_time_per_question > 120:  # >2 minutes per question
                # Reduce questions if taking too long (fatigue)
                config['num_questions'] = max(5, base_questions - 2)
            elif profile.average_time_per_question < 30:  # <30 seconds per question
                # Increase questions if answering quickly
                config['num_questions'] = min(20, base_questions + 2)
        
        # Adjust based on learning velocity
        if profile.learning_velocity > 0.1:  # Improving rapidly
            config['num_questions'] = min(20, base_questions + 3)
        elif profile.learning_velocity < -0.1:  # Declining performance
            config['num_questions'] = max(5, base_questions - 3)
        
        return config
    
    def _select_question_types(self, config: Dict, 
                              profile: LearnerProfile) -> Dict:
        """Select question types based on learner preferences"""
        
        if profile.preferred_question_types:
            # Weight preferred types higher
            weighted_types = []
            
            for q_type in config.get('question_types', ['multiple_choice', 'short_answer']):
                weight = 2 if q_type in profile.preferred_question_types else 1
                weighted_types.extend([q_type] * weight)
            
            config['question_types'] = weighted_types
        
        return config
    
    def _identify_strengths_weaknesses(self, profile: LearnerProfile) -> None:
        """Identify learner's strengths and weaknesses"""
        
        if not profile.topics_mastery:
            return
        
        sorted_topics = sorted(profile.topics_mastery.items(), 
                              key=lambda x: x[1], reverse=True)
        
        # Top 3 topics are strengths
        profile.strengths = [topic for topic, _ in sorted_topics[:3] if _ > 0.7]
        
        # Bottom 3 topics are weaknesses
        profile.weaknesses = [topic for topic, _ in sorted_topics[-3:] if _ < 0.6]
    
    def _calculate_learning_velocity(self, history: Dict) -> float:
        """Calculate rate of improvement over recent sessions"""
        
        if 'recent_sessions' not in history or len(history['recent_sessions']) < 2:
            return 0
        
        sessions = history['recent_sessions']
        
        # Calculate performance trend
        performances = [s.get('accuracy', 0) for s in sessions]
        
        if len(performances) < 2:
            return 0
        
        # Simple linear regression for trend
        x = np.arange(len(performances))
        y = np.array(performances)
        
        # Calculate slope
        slope = np.polyfit(x, y, 1)[0]
        
        return slope
    
    def update_user_model(self, user_id: str, quiz_report: Dict) -> None:
        """Update user model after quiz completion"""
        
        profile = self.get_or_create_profile(user_id)
        
        # Update basic stats
        profile.total_questions_answered += quiz_report.get('total_questions', 0)
        profile.correct_answers += quiz_report.get('correct_answers', 0)
        
        # Update topic mastery
        for topic, performance in quiz_report.get('topic_scores', {}).items():
            if topic not in profile.topics_mastery:
                profile.topics_mastery[topic] = performance
            else:
                # Weighted average with recency bias
                profile.topics_mastery[topic] = (
                    0.6 * profile.topics_mastery[topic] + 0.4 * performance
                )
        
        # Update Bloom performance
        for bloom_level, performance in quiz_report.get('bloom_scores', {}).items():
            if bloom_level not in profile.bloom_performance:
                profile.bloom_performance[bloom_level] = performance
            else:
                profile.bloom_performance[bloom_level] = (
                    0.6 * profile.bloom_performance[bloom_level] + 0.4 * performance
                )
        
        # Update timing
        if 'average_time' in quiz_report:
            if profile.average_time_per_question == 0:
                profile.average_time_per_question = quiz_report['average_time']
            else:
                profile.average_time_per_question = (
                    0.7 * profile.average_time_per_question + 0.3 * quiz_report['average_time']
                )
        
        profile.last_session = datetime.now()
        
        # Recalculate strengths and weaknesses
        self._identify_strengths_weaknesses(profile)
        
        logger.info(f"Updated model for user {user_id}")
    
    def get_recommendations(self, question_topic: str, 
                           performance: float) -> List[str]:
        """Get learning recommendations based on performance"""
        
        recommendations = []
        
        if performance < 0.4:
            recommendations.extend([
                f"Review fundamental concepts of {question_topic}",
                f"Practice more basic {question_topic} problems",
                "Consider watching introductory videos on this topic"
            ])
        elif performance < 0.7:
            recommendations.extend([
                f"Focus on understanding {question_topic} applications",
                "Try solving varied problem types",
                "Review your notes and attempt practice exercises"
            ])
        else:
            recommendations.extend([
                f"Challenge yourself with advanced {question_topic} problems",
                "Try teaching this concept to someone else",
                "Explore real-world applications"
            ])
        
        return recommendations
    
    def generate_study_plan(self, user_id: str, performance: Dict) -> Dict:
        """Generate personalized study plan based on performance"""
        
        profile = self.get_or_create_profile(user_id)
        
        study_plan = {
            'immediate_focus': [],
            'short_term_goals': [],
            'long_term_goals': [],
            'recommended_resources': [],
            'practice_schedule': {}
        }
        
        # Immediate focus on weaknesses
        for topic in profile.weaknesses[:3]:
            study_plan['immediate_focus'].append({
                'topic': topic,
                'mastery': profile.topics_mastery.get(topic, 0),
                'target': 0.7,
                'estimated_time': '30-45 minutes',
                'resources': self._get_topic_resources(topic)
            })
        
        # Short-term goals (1 week)
        study_plan['short_term_goals'] = [
            f"Achieve 70% mastery in {', '.join(profile.weaknesses[:2])}",
            "Complete 50 practice questions",
            "Review all incorrect answers from recent quizzes"
        ]
        
        # Long-term goals (1 month)
        study_plan['long_term_goals'] = [
            "Achieve 80% overall accuracy",
            f"Master all topics to at least 60% proficiency",
            "Progress to higher-order thinking questions"
        ]
        
        # Practice schedule using spaced repetition
        study_plan['practice_schedule'] = self._generate_practice_schedule(profile)
        
        # Recommended resources
        study_plan['recommended_resources'] = [
            {"type": "video", "topic": w, "url": f"#video-{w}"} 
            for w in profile.weaknesses
        ]
        
        return study_plan
    
    def _generate_practice_schedule(self, profile: LearnerProfile) -> Dict:
        """Generate spaced repetition practice schedule"""
        
        schedule = {}
        today = datetime.now()
        
        for topic, mastery in profile.topics_mastery.items():
            # Calculate review intervals based on mastery
            if mastery < 0.4:
                intervals = [1, 2, 4, 7]  # More frequent for weak topics
            elif mastery < 0.7:
                intervals = [2, 5, 10, 20]
            else:
                intervals = [7, 14, 30, 60]  # Less frequent for strong topics
            
            schedule[topic] = [
                (today + timedelta(days=d)).strftime('%Y-%m-%d') 
                for d in intervals
            ]
        
        return schedule
    
    def _get_topic_resources(self, topic: str) -> List[Dict]:
        """Get learning resources for a topic"""
        
        # In a real implementation, this would query a resource database
        return [
            {"type": "article", "title": f"Understanding {topic}", "url": "#"},
            {"type": "video", "title": f"{topic} Explained", "url": "#"},
            {"type": "exercise", "title": f"Practice {topic}", "url": "#"}
        ]
    
    def export_profile(self, user_id: str) -> Dict:
        """Export user profile for persistence"""
        
        profile = self.get_or_create_profile(user_id)
        
        return {
            'user_id': profile.user_id,
            'total_questions': profile.total_questions_answered,
            'correct_answers': profile.correct_answers,
            'accuracy': profile.correct_answers / max(1, profile.total_questions_answered),
            'topics_mastery': profile.topics_mastery,
            'bloom_performance': profile.bloom_performance,
            'strengths': profile.strengths,
            'weaknesses': profile.weaknesses,
            'last_session': profile.last_session.isoformat() if profile.last_session else None,
            'learning_velocity': profile.learning_velocity,
            'performance_level': self._calculate_performance_level(profile).value
        }
    
    def import_profile(self, profile_data: Dict) -> None:
        """Import user profile from saved data"""
        
        user_id = profile_data['user_id']
        profile = LearnerProfile(
            user_id=user_id,
            total_questions_answered=profile_data.get('total_questions', 0),
            correct_answers=profile_data.get('correct_answers', 0),
            topics_mastery=profile_data.get('topics_mastery', {}),
            bloom_performance=profile_data.get('bloom_performance', {}),
            strengths=profile_data.get('strengths', []),
            weaknesses=profile_data.get('weaknesses', []),
            learning_velocity=profile_data.get('learning_velocity', 0)
        )
        
        if profile_data.get('last_session'):
            profile.last_session = datetime.fromisoformat(profile_data['last_session'])
        
        self.learner_profiles[user_id] = profile
