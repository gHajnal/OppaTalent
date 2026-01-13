"""
Canvas LTI Integration Module
Handles Learning Tools Interoperability for Canvas LMS integration
"""

import os
import json
import hmac
import hashlib
import base64
from typing import Dict, Optional, List
from datetime import datetime
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, parse_qs
import logging

from oauthlib.oauth1 import Client, SIGNATURE_HMAC_SHA1
import requests

logger = logging.getLogger(__name__)

class CanvasLTIProvider:
    """
    LTI Provider for Canvas LMS integration
    Supports LTI 1.1 and basic LTI 1.3
    """
    
    def __init__(self, consumer_key: Optional[str] = None, 
                 consumer_secret: Optional[str] = None):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.canvas_api_url = os.environ.get('CANVAS_API_URL', 'https://canvas.instructure.com/api/v1')
        self.canvas_token = os.environ.get('CANVAS_API_TOKEN')
        
    def validate_request(self, request) -> bool:
        """
        Validate LTI launch request from Canvas
        """
        try:
            # Get OAuth parameters from request
            oauth_params = {
                'oauth_consumer_key': request.form.get('oauth_consumer_key'),
                'oauth_signature_method': request.form.get('oauth_signature_method'),
                'oauth_timestamp': request.form.get('oauth_timestamp'),
                'oauth_nonce': request.form.get('oauth_nonce'),
                'oauth_version': request.form.get('oauth_version', '1.0'),
                'oauth_signature': request.form.get('oauth_signature')
            }
            
            # Verify consumer key
            if oauth_params['oauth_consumer_key'] != self.consumer_key:
                logger.warning("Invalid consumer key")
                return False
            
            # Verify signature
            client = Client(
                client_key=self.consumer_key,
                client_secret=self.consumer_secret,
                signature_method=SIGNATURE_HMAC_SHA1
            )
            
            # Build base string for signature
            uri = request.url
            http_method = request.method
            
            # Remove oauth_signature from params for verification
            params = dict(request.form)
            if 'oauth_signature' in params:
                del params['oauth_signature']
            
            # Generate signature
            signature = client.sign(
                uri=uri,
                http_method=http_method,
                body=params,
                headers=request.headers
            )
            
            # Compare signatures
            provided_signature = oauth_params['oauth_signature']
            
            return hmac.compare_digest(signature[1], provided_signature)
            
        except Exception as e:
            logger.error(f"LTI validation error: {str(e)}")
            return False
    
    def extract_launch_data(self, request) -> Dict:
        """
        Extract relevant data from LTI launch request
        """
        data = {
            # User information
            'user_id': request.form.get('user_id'),
            'user_name': request.form.get('lis_person_name_full'),
            'user_email': request.form.get('lis_person_contact_email_primary'),
            'user_roles': request.form.get('roles', '').split(','),
            
            # Course information
            'course_id': request.form.get('context_id'),
            'course_title': request.form.get('context_title'),
            'course_label': request.form.get('context_label'),
            
            # Assignment information
            'resource_link_id': request.form.get('resource_link_id'),
            'resource_link_title': request.form.get('resource_link_title'),
            'resource_link_description': request.form.get('resource_link_description'),
            
            # Grade passback
            'lis_outcome_service_url': request.form.get('lis_outcome_service_url'),
            'lis_result_sourcedid': request.form.get('lis_result_sourcedid'),
            
            # Canvas specific
            'canvas_user_id': request.form.get('custom_canvas_user_id'),
            'canvas_course_id': request.form.get('custom_canvas_course_id'),
            'canvas_assignment_id': request.form.get('custom_canvas_assignment_id'),
            
            # Launch presentation
            'launch_presentation_return_url': request.form.get('launch_presentation_return_url'),
            'launch_presentation_locale': request.form.get('launch_presentation_locale', 'en'),
            
            # Tool consumer info
            'tool_consumer_instance_guid': request.form.get('tool_consumer_instance_guid'),
            'tool_consumer_instance_name': request.form.get('tool_consumer_instance_name')
        }
        
        return data
    
    def send_grade(self, score: float, outcome_url: str, 
                   sourcedid: str) -> bool:
        """
        Send grade back to Canvas gradebook
        """
        try:
            # Build XML for grade submission
            xml_template = """<?xml version="1.0" encoding="UTF-8"?>
            <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
                <imsx_POXHeader>
                    <imsx_POXRequestHeaderInfo>
                        <imsx_version>V1.0</imsx_version>
                        <imsx_messageIdentifier>{message_id}</imsx_messageIdentifier>
                    </imsx_POXRequestHeaderInfo>
                </imsx_POXHeader>
                <imsx_POXBody>
                    <replaceResultRequest>
                        <resultRecord>
                            <sourcedGUID>
                                <sourcedId>{sourcedid}</sourcedId>
                            </sourcedGUID>
                            <result>
                                <resultScore>
                                    <language>en</language>
                                    <textString>{score}</textString>
                                </resultScore>
                            </result>
                        </resultRecord>
                    </replaceResultRequest>
                </imsx_POXBody>
            </imsx_POXEnvelopeRequest>"""
            
            # Generate message ID
            message_id = f"smartquiz_{datetime.utcnow().timestamp()}"
            
            # Format XML
            xml_data = xml_template.format(
                message_id=message_id,
                sourcedid=sourcedid,
                score=min(1.0, max(0.0, score))  # Ensure score is between 0 and 1
            )
            
            # Sign request
            client = Client(
                client_key=self.consumer_key,
                client_secret=self.consumer_secret,
                signature_method=SIGNATURE_HMAC_SHA1
            )
            
            # Send POST request
            headers = {
                'Content-Type': 'application/xml',
                'Accept': 'application/xml'
            }
            
            # Add OAuth headers
            uri, headers, body = client.sign(
                uri=outcome_url,
                http_method='POST',
                body=xml_data,
                headers=headers
            )
            
            response = requests.post(
                outcome_url,
                data=xml_data,
                headers=headers
            )
            
            # Parse response
            if response.status_code == 200:
                root = ET.fromstring(response.text)
                
                # Check for success
                status_node = root.find('.//{http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0}imsx_codeMajor')
                
                if status_node is not None and status_node.text == 'success':
                    logger.info(f"Grade {score} sent successfully")
                    return True
            
            logger.warning(f"Grade submission failed: {response.status_code}")
            return False
            
        except Exception as e:
            logger.error(f"Error sending grade: {str(e)}")
            return False
    
    def format_quiz(self, quiz: Dict) -> Dict:
        """
        Format quiz for Canvas quiz import
        """
        canvas_quiz = {
            'title': quiz.get('title', 'AI Generated Quiz'),
            'description': quiz.get('description', ''),
            'quiz_type': 'assignment',
            'time_limit': quiz.get('metadata', {}).get('estimated_time', 30),
            'shuffle_answers': True,
            'show_correct_answers': True,
            'show_correct_answers_at': 'after_submission',
            'scoring_policy': 'keep_highest',
            'allowed_attempts': -1,  # Unlimited
            'questions': []
        }
        
        # Convert questions to Canvas format
        for q in quiz.get('questions', []):
            canvas_q = self._format_question(q)
            if canvas_q:
                canvas_quiz['questions'].append(canvas_q)
        
        return canvas_quiz
    
    def _format_question(self, question: Dict) -> Dict:
        """
        Format individual question for Canvas
        """
        q_type = question.get('type')
        
        canvas_q = {
            'question_name': question.get('id'),
            'question_text': question.get('question'),
            'points_possible': 1,
            'correct_comments': question.get('explanation', ''),
            'incorrect_comments': 'Review this topic and try again.'
        }
        
        if q_type == 'multiple_choice':
            canvas_q['question_type'] = 'multiple_choice_question'
            canvas_q['answers'] = []
            
            correct_answer = question.get('correct_answer')
            options = question.get('options', [])
            
            for i, option in enumerate(options):
                answer = {
                    'answer_text': option,
                    'answer_weight': 100 if option.startswith(correct_answer) else 0
                }
                canvas_q['answers'].append(answer)
        
        elif q_type == 'true_false':
            canvas_q['question_type'] = 'true_false_question'
            correct = question.get('correct_answer', '').lower() == 'true'
            canvas_q['answers'] = [
                {'answer_text': 'True', 'answer_weight': 100 if correct else 0},
                {'answer_text': 'False', 'answer_weight': 0 if correct else 100}
            ]
        
        elif q_type == 'short_answer':
            canvas_q['question_type'] = 'short_answer_question'
            canvas_q['answers'] = [
                {'answer_text': question.get('correct_answer'), 'answer_weight': 100}
            ]
        
        elif q_type == 'essay':
            canvas_q['question_type'] = 'essay_question'
            # Essay questions don't have automated grading
        
        else:
            # Default to text entry
            canvas_q['question_type'] = 'short_answer_question'
            canvas_q['answers'] = [
                {'answer_text': question.get('correct_answer'), 'answer_weight': 100}
            ]
        
        return canvas_q
    
    def create_canvas_quiz(self, course_id: str, quiz_data: Dict) -> Optional[Dict]:
        """
        Create a quiz directly in Canvas using API
        """
        if not self.canvas_token:
            logger.warning("Canvas API token not configured")
            return None
        
        try:
            url = f"{self.canvas_api_url}/courses/{course_id}/quizzes"
            
            headers = {
                'Authorization': f'Bearer {self.canvas_token}',
                'Content-Type': 'application/json'
            }
            
            # Format quiz data for Canvas API
            canvas_quiz = self.format_quiz(quiz_data)
            
            payload = {
                'quiz': {
                    'title': canvas_quiz['title'],
                    'description': canvas_quiz['description'],
                    'quiz_type': canvas_quiz['quiz_type'],
                    'time_limit': canvas_quiz['time_limit'],
                    'shuffle_answers': canvas_quiz['shuffle_answers'],
                    'show_correct_answers': canvas_quiz['show_correct_answers'],
                    'scoring_policy': canvas_quiz['scoring_policy'],
                    'allowed_attempts': canvas_quiz['allowed_attempts'],
                    'published': False  # Create as draft
                }
            }
            
            # Create quiz
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 201:
                quiz = response.json()
                quiz_id = quiz['id']
                
                # Add questions to quiz
                for q in canvas_quiz['questions']:
                    self._add_question_to_quiz(course_id, quiz_id, q)
                
                logger.info(f"Quiz created in Canvas: {quiz_id}")
                return quiz
            else:
                logger.error(f"Failed to create Canvas quiz: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating Canvas quiz: {str(e)}")
            return None
    
    def _add_question_to_quiz(self, course_id: str, quiz_id: str, 
                             question: Dict) -> bool:
        """
        Add a question to an existing Canvas quiz
        """
        try:
            url = f"{self.canvas_api_url}/courses/{course_id}/quizzes/{quiz_id}/questions"
            
            headers = {
                'Authorization': f'Bearer {self.canvas_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {'question': question}
            
            response = requests.post(url, json=payload, headers=headers)
            
            return response.status_code == 201
            
        except Exception as e:
            logger.error(f"Error adding question to quiz: {str(e)}")
            return False
    
    def get_student_submissions(self, course_id: str, 
                               assignment_id: str) -> List[Dict]:
        """
        Get student submissions for a quiz/assignment
        """
        if not self.canvas_token:
            return []
        
        try:
            url = f"{self.canvas_api_url}/courses/{course_id}/assignments/{assignment_id}/submissions"
            
            headers = {
                'Authorization': f'Bearer {self.canvas_token}'
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Failed to get submissions: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting submissions: {str(e)}")
            return []
    
    def export_to_common_cartridge(self, quiz: Dict) -> str:
        """
        Export quiz to Common Cartridge format for LMS import
        """
        # Common Cartridge is a standard format for course content
        # This is a simplified version
        
        cc_template = """<?xml version="1.0" encoding="UTF-8"?>
        <manifest identifier="smartquiz_export" version="1.3"
                  xmlns="http://www.imsglobal.org/xsd/imsccv1p3/imscp_v1p1">
            <metadata>
                <schema>IMS Common Cartridge</schema>
                <schemaversion>1.3.0</schemaversion>
            </metadata>
            <organizations>
                <organization identifier="org_1">
                    <item identifier="quiz_1" identifierref="quiz_resource">
                        <title>{title}</title>
                    </item>
                </organization>
            </organizations>
            <resources>
                <resource identifier="quiz_resource" type="imsqti_xmlv1p2">
                    <file href="quiz.xml"/>
                </resource>
            </resources>
        </manifest>"""
        
        return cc_template.format(title=quiz.get('title', 'Quiz'))
    
    def validate_canvas_connection(self) -> bool:
        """
        Validate Canvas API connection
        """
        if not self.canvas_token:
            return False
        
        try:
            url = f"{self.canvas_api_url}/users/self"
            headers = {'Authorization': f'Bearer {self.canvas_token}'}
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                user = response.json()
                logger.info(f"Canvas connection validated for user: {user.get('name')}")
                return True
            else:
                logger.warning(f"Canvas connection failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Canvas connection error: {str(e)}")
            return False
