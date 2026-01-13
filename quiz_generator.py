"""
Quiz Generator Module
Handles AI-powered quiz generation with educational best practices
"""

import os
import json
import time
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import tiktoken
from dataclasses import dataclass
from enum import Enum

import openai
from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate, ChatPromptTemplate
from langchain.chains import LLMChain
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import spacy

# Load spaCy model for NLP tasks
try:
    nlp = spacy.load("en_core_web_sm")
except:
    os.system("python -m spacy download en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"
    FILL_BLANK = "fill_blank"

class BloomLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"

@dataclass
class Question:
    id: str
    type: QuestionType
    bloom_level: BloomLevel
    question_text: str
    options: Optional[List[str]] = None
    correct_answer: str = ""
    explanation: str = ""
    hint: Optional[str] = None
    difficulty: int = 3  # 1-5 scale
    topic: str = ""
    estimated_time: int = 90  # seconds

class QuizOutput(BaseModel):
    questions: List[Dict] = Field(description="List of quiz questions")
    metadata: Dict = Field(description="Quiz metadata")

class QuizGenerator:
    """Advanced AI-powered quiz generator with educational principles"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4"):
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        openai.api_key = self.api_key
        self.model = model
        
        # Initialize LangChain
        self.llm = ChatOpenAI(
            model_name=model,
            temperature=0.7,
            openai_api_key=self.api_key
        )
        
        # Token tracking
        self.encoder = tiktoken.encoding_for_model(model if 'gpt' in model else 'gpt-4')
        self.total_tokens_used = 0
        self.total_cost = 0.0
        self.requests_today = 0
        self.response_times = []
        self.last_token_usage = 0
        
        # Bloom's Taxonomy templates
        self.bloom_templates = self._load_bloom_templates()
        
        # Output parser
        self.parser = PydanticOutputParser(pydantic_object=QuizOutput)
    
    def _load_bloom_templates(self) -> Dict[str, str]:
        """Load question templates for each Bloom's level"""
        return {
            BloomLevel.REMEMBER: """
                Create recall-based questions:
                - "What is the definition of..."
                - "List the main components of..."
                - "When did ... occur?"
                - "Who discovered/invented..."
            """,
            BloomLevel.UNDERSTAND: """
                Create comprehension questions:
                - "Explain in your own words..."
                - "What is the main idea of..."
                - "Compare and contrast..."
                - "Give an example of..."
            """,
            BloomLevel.APPLY: """
                Create application questions:
                - "How would you use ... to solve..."
                - "What would happen if..."
                - "Apply the concept to a new situation..."
                - "Demonstrate how..."
            """,
            BloomLevel.ANALYZE: """
                Create analytical questions:
                - "What are the causes of..."
                - "How does ... relate to..."
                - "What evidence supports..."
                - "What are the implications of..."
            """,
            BloomLevel.EVALUATE: """
                Create evaluation questions:
                - "What is your opinion on..."
                - "Critique the argument that..."
                - "Which solution is best and why..."
                - "Assess the effectiveness of..."
            """,
            BloomLevel.CREATE: """
                Create synthesis questions:
                - "Design a solution for..."
                - "Propose an alternative to..."
                - "Develop a plan to..."
                - "Create a new approach to..."
            """
        }
    
    def check_connection(self) -> bool:
        """Check if OpenAI API is accessible"""
        try:
            openai.Model.list()
            return True
        except:
            return False
    
    def analyze_content(self, content: str) -> Dict:
        """
        Analyze content to extract topics, difficulty, and key concepts
        Uses NLP and AI to understand the material
        """
        start_time = time.time()
        
        # Use spaCy for initial analysis
        doc = nlp(content[:1000000])  # Limit to 1M chars for spaCy
        
        # Extract entities and key phrases
        entities = [ent.text for ent in doc.ents]
        noun_phrases = [chunk.text for chunk in doc.noun_chunks][:20]
        
        # AI-powered deep analysis
        prompt = f"""
        Analyze this educational content and provide a JSON response with:
        1. Main topics (list of 3-5 topics)
        2. Key concepts that should be tested (list of 5-10 concepts)
        3. Difficulty level (beginner/intermediate/advanced)
        4. Suggested number of questions (based on content depth)
        5. Content type (technical/theoretical/practical/mixed)
        
        Content preview: {content[:2000]}...
        
        Response format:
        {{
            "topics": ["topic1", "topic2"],
            "key_concepts": ["concept1", "concept2"],
            "difficulty": "intermediate",
            "possible_questions": 10,
            "content_type": "technical"
        }}
        """
        
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert educational content analyzer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            analysis = json.loads(response.choices[0].message.content)
            
            # Add NLP-extracted data
            analysis['entities'] = list(set(entities))[:10]
            analysis['key_phrases'] = noun_phrases
            
            # Track usage
            self._track_usage(response)
            
        except Exception as e:
            # Fallback analysis
            analysis = {
                "topics": noun_phrases[:5] if noun_phrases else ["General"],
                "key_concepts": entities[:10] if entities else ["Key concepts"],
                "difficulty": "intermediate",
                "possible_questions": min(10, len(content.split()) // 100),
                "content_type": "mixed"
            }
        
        self.response_times.append(time.time() - start_time)
        return analysis
    
    def generate_quiz(self, content: str, config: Dict) -> Dict:
        """
        Generate a comprehensive quiz with multiple question types
        Implements Bloom's Taxonomy and adaptive difficulty
        """
        start_time = time.time()
        
        num_questions = config.get('num_questions', 10)
        difficulty_dist = config.get('difficulty_distribution', {
            'remember': 0.2,
            'understand': 0.3,
            'apply': 0.3,
            'analyze': 0.2
        })
        
        # Calculate questions per Bloom level
        bloom_counts = {
            level: int(num_questions * ratio) 
            for level, ratio in difficulty_dist.items()
        }
        
        # Ensure we have exactly num_questions
        diff = num_questions - sum(bloom_counts.values())
        if diff > 0:
            bloom_counts['understand'] += diff
        
        # Generate comprehensive prompt
        prompt = self._create_quiz_prompt(content, bloom_counts, config)
        
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": """You are an expert educator and quiz designer. 
                        Create educationally sound questions following Bloom's Taxonomy.
                        Ensure questions are clear, unambiguous, and test real understanding.
                        Include detailed explanations for learning."""
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4000
            )
            
            quiz_text = response.choices[0].message.content
            
            # Parse and structure the quiz
            quiz = self._parse_quiz_response(quiz_text)
            
            # Add educational metadata
            quiz['metadata'] = {
                'bloom_distribution': bloom_counts,
                'config': config,
                'content_length': len(content),
                'generation_time': time.time() - start_time
            }
            
            # Track usage
            self._track_usage(response)
            
        except Exception as e:
            # Fallback quiz generation
            quiz = self._generate_fallback_quiz(content, config)
        
        self.response_times.append(time.time() - start_time)
        return quiz
    
    def _create_quiz_prompt(self, content: str, bloom_counts: Dict, config: Dict) -> str:
        """Create detailed prompt for quiz generation"""
        
        # Truncate content if too long
        max_content_tokens = 2000
        content_tokens = self.encoder.encode(content)
        if len(content_tokens) > max_content_tokens:
            content = self.encoder.decode(content_tokens[:max_content_tokens])
        
        prompt = f"""
        Create a quiz based on this educational content:
        
        {content}
        
        Requirements:
        1. Generate exactly {sum(bloom_counts.values())} questions
        2. Question distribution by Bloom's Taxonomy:
           - Remember: {bloom_counts.get('remember', 0)} questions
           - Understand: {bloom_counts.get('understand', 0)} questions
           - Apply: {bloom_counts.get('apply', 0)} questions
           - Analyze: {bloom_counts.get('analyze', 0)} questions
        
        3. Include these question types:
           - Multiple choice (4 options, with plausible distractors)
           - True/False (with explanations)
           - Short answer (1-2 sentences expected)
           
        4. For each question provide:
           - Question text
           - Question type
           - Bloom's level
           - Options (for multiple choice)
           - Correct answer
           - Detailed explanation (2-3 sentences)
           - Hint (optional, helpful guidance)
           - Difficulty (1-5 scale)
           - Topic/concept tested
        
        5. Educational best practices:
           - Avoid negative phrasing ("Which is NOT...")
           - Make distractors plausible but clearly wrong
           - Test understanding, not memorization
           - Include real-world applications where possible
        
        Format as JSON:
        {{
            "questions": [
                {{
                    "id": "q1",
                    "type": "multiple_choice",
                    "bloom_level": "understand",
                    "question": "...",
                    "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
                    "correct_answer": "A",
                    "explanation": "...",
                    "hint": "...",
                    "difficulty": 3,
                    "topic": "..."
                }}
            ]
        }}
        """
        
        return prompt
    
    def validate_answer(self, question: str, correct_answer: str, 
                       user_answer: str, rubric: Optional[Dict] = None) -> Dict:
        """
        Validate user answer with semantic understanding
        Provides partial credit and detailed feedback
        """
        start_time = time.time()
        
        prompt = f"""
        Evaluate this answer for correctness and completeness.
        
        Question: {question}
        Expected Answer: {correct_answer}
        Student Answer: {user_answer}
        
        Evaluation criteria:
        1. Factual accuracy
        2. Completeness of response
        3. Understanding of concepts
        4. Use of appropriate terminology
        
        Provide:
        1. Score (0.0 to 1.0)
        2. Whether essentially correct (boolean)
        3. Specific feedback
        4. What's missing (if applicable)
        5. What's incorrect (if applicable)
        
        Return as JSON:
        {{
            "score": 0.0-1.0,
            "is_correct": true/false,
            "feedback": "specific feedback",
            "missing_elements": ["element1", "element2"],
            "misconceptions": ["misconception1"],
            "suggestions": ["suggestion1"]
        }}
        """
        
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an expert educator providing constructive feedback."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            validation = json.loads(response.choices[0].message.content)
            
            # Add encouragement based on score
            if validation['score'] >= 0.8:
                validation['encouragement'] = "Excellent work! You demonstrate strong understanding."
            elif validation['score'] >= 0.6:
                validation['encouragement'] = "Good effort! Review the feedback to strengthen your understanding."
            else:
                validation['encouragement'] = "Keep practicing! Use the feedback to improve."
            
            self._track_usage(response)
            
        except Exception as e:
            # Fallback validation
            validation = self._simple_validation(user_answer, correct_answer)
        
        validation['response_time'] = time.time() - start_time
        return validation
    
    def generate_study_guide(self, content: str, weak_areas: List[str], 
                           performance: float) -> Dict:
        """Generate personalized study guide based on performance"""
        
        prompt = f"""
        Create a personalized study guide based on quiz performance.
        
        Original content topics: {content[:500]}...
        Weak areas identified: {', '.join(weak_areas)}
        Overall performance: {performance:.1%}
        
        Generate:
        1. Key concepts to review (prioritized by weakness)
        2. Study strategies specific to the content
        3. Practice exercises for weak areas
        4. Resources and examples
        5. Estimated study time needed
        
        Format as structured study plan with clear sections.
        """
        
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert tutor creating personalized study plans."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=1500
            )
            
            study_guide = {
                'content': response.choices[0].message.content,
                'weak_areas': weak_areas,
                'recommended_review_time': len(weak_areas) * 15,  # 15 min per topic
                'performance_level': performance
            }
            
            self._track_usage(response)
            
        except Exception as e:
            study_guide = {
                'content': f"Focus on these areas: {', '.join(weak_areas)}",
                'weak_areas': weak_areas,
                'recommended_review_time': 30,
                'performance_level': performance
            }
        
        return study_guide
    
    def export_to_qti(self, quiz: Dict) -> str:
        """Export quiz to QTI format for LMS import"""
        # QTI (Question and Test Interoperability) format
        qti_template = """<?xml version="1.0" encoding="UTF-8"?>
        <questestinterop xmlns="http://www.imsglobal.org/xsd/ims_qtiasiv1p2">
            <assessment title="AI Generated Quiz">
                {questions}
            </assessment>
        </questestinterop>"""
        
        questions_xml = []
        for q in quiz.get('questions', []):
            if q['type'] == 'multiple_choice':
                question_xml = self._create_qti_mc_question(q)
            else:
                question_xml = self._create_qti_text_question(q)
            questions_xml.append(question_xml)
        
        return qti_template.format(questions='\n'.join(questions_xml))
    
    def _create_qti_mc_question(self, question: Dict) -> str:
        """Create QTI format for multiple choice question"""
        return f"""
        <item ident="{question['id']}" title="Question">
            <itemmetadata>
                <qtimetadata>
                    <qtimetadatafield>
                        <fieldlabel>question_type</fieldlabel>
                        <fieldentry>multiple_choice_question</fieldentry>
                    </qtimetadatafield>
                </qtimetadata>
            </itemmetadata>
            <presentation>
                <material>
                    <mattext texttype="text/html">{question['question']}</mattext>
                </material>
                <response_lid ident="response1" rcardinality="Single">
                    <render_choice>
                        {self._create_qti_choices(question['options'])}
                    </render_choice>
                </response_lid>
            </presentation>
        </item>
        """
    
    def _create_qti_choices(self, options: List[str]) -> str:
        """Create QTI choice options"""
        choices = []
        for i, option in enumerate(options):
            choices.append(f"""
                <response_label ident="choice_{i}">
                    <material>
                        <mattext>{option}</mattext>
                    </material>
                </response_label>
            """)
        return '\n'.join(choices)
    
    def _create_qti_text_question(self, question: Dict) -> str:
        """Create QTI format for text question"""
        return f"""
        <item ident="{question['id']}" title="Question">
            <presentation>
                <material>
                    <mattext texttype="text/html">{question['question']}</mattext>
                </material>
                <response_str ident="response1" rcardinality="Single">
                    <render_fib>
                        <response_label ident="answer1" rshuffle="No"/>
                    </render_fib>
                </response_str>
            </presentation>
        </item>
        """
    
    def _parse_quiz_response(self, response_text: str) -> Dict:
        """Parse AI response into structured quiz format"""
        try:
            # Try to parse as JSON
            if '{' in response_text and '}' in response_text:
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                json_text = response_text[json_start:json_end]
                return json.loads(json_text)
        except:
            pass
        
        # Fallback parsing
        return self._generate_fallback_quiz("", {"num_questions": 5})
    
    def _generate_fallback_quiz(self, content: str, config: Dict) -> Dict:
        """Generate a simple fallback quiz if AI fails"""
        return {
            "questions": [
                {
                    "id": f"q{i}",
                    "type": "multiple_choice",
                    "bloom_level": "remember",
                    "question": f"Sample question {i} about the content",
                    "options": ["Option A", "Option B", "Option C", "Option D"],
                    "correct_answer": "A",
                    "explanation": "This is a fallback question.",
                    "difficulty": 3,
                    "topic": "General"
                } for i in range(1, config.get('num_questions', 5) + 1)
            ],
            "metadata": {
                "fallback": True,
                "reason": "AI generation failed"
            }
        }
    
    def _simple_validation(self, user_answer: str, correct_answer: str) -> Dict:
        """Simple string-based validation fallback"""
        user_lower = user_answer.lower().strip()
        correct_lower = correct_answer.lower().strip()
        
        # Check exact match
        if user_lower == correct_lower:
            return {
                "score": 1.0,
                "is_correct": True,
                "feedback": "Correct!",
                "missing_elements": [],
                "misconceptions": []
            }
        
        # Check partial match
        if user_lower in correct_lower or correct_lower in user_lower:
            return {
                "score": 0.5,
                "is_correct": False,
                "feedback": "Partially correct. Review the complete answer.",
                "missing_elements": ["Complete answer"],
                "misconceptions": []
            }
        
        return {
            "score": 0.0,
            "is_correct": False,
            "feedback": f"Incorrect. The correct answer is: {correct_answer}",
            "missing_elements": ["Correct answer"],
            "misconceptions": ["Review this topic"]
        }
    
    def _track_usage(self, response) -> None:
        """Track API usage and costs"""
        try:
            usage = response.get('usage', {})
            tokens = usage.get('total_tokens', 0)
            self.total_tokens_used += tokens
            self.last_token_usage = tokens
            
            # Estimate costs (GPT-4 pricing as of 2024)
            if 'gpt-4' in self.model:
                input_cost = usage.get('prompt_tokens', 0) * 0.03 / 1000
                output_cost = usage.get('completion_tokens', 0) * 0.06 / 1000
            else:  # GPT-3.5
                input_cost = usage.get('prompt_tokens', 0) * 0.001 / 1000
                output_cost = usage.get('completion_tokens', 0) * 0.002 / 1000
            
            self.total_cost += (input_cost + output_cost)
            self.requests_today += 1
        except:
            pass
    
    def calculate_cost(self, tokens: int) -> float:
        """Calculate estimated cost for token usage"""
        if 'gpt-4' in self.model:
            return tokens * 0.045 / 1000  # Average of input/output
        else:
            return tokens * 0.0015 / 1000
    
    @property
    def avg_response_time(self) -> float:
        """Calculate average response time"""
        if not self.response_times:
            return 0
        return sum(self.response_times) / len(self.response_times)
