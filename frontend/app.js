/**
 * OppaTalent Quiz Generator - Frontend Application
 * AI-powered adaptive quiz generation system
 */

function quizApp() {
    return {
        // Application state
        currentStep: 'upload',
        loading: false,
        dragover: false,
        selectedFile: null,
        
        // Quiz settings
        settings: {
            numQuestions: 10,
            mode: 'adaptive',
            includeHints: true,
            includeExplanations: true
        },
        
        // Bloom's taxonomy levels
        bloomLevels: [
            { name: 'remember', label: 'Remember', enabled: true, percentage: 20 },
            { name: 'understand', label: 'Understand', enabled: true, percentage: 30 },
            { name: 'apply', label: 'Apply', enabled: true, percentage: 30 },
            { name: 'analyze', label: 'Analyze', enabled: true, percentage: 20 },
            { name: 'evaluate', label: 'Evaluate', enabled: false, percentage: 0 },
            { name: 'create', label: 'Create', enabled: false, percentage: 0 }
        ],
        
        // Quiz data
        quiz: null,
        currentQuestionIndex: 0,
        currentQuestion: null,
        answers: [],
        
        // Quiz state
        selectedAnswer: null,
        shortAnswer: '',
        answered: false,
        showFeedback: false,
        isCorrect: false,
        
        // Scoring
        score: 0,
        correctAnswers: 0,
        streak: 0,
        longestStreak: 0,
        
        // Timing
        quizStartTime: null,
        questionStartTime: null,
        totalTime: 0,
        avgTimePerQuestion: 0,
        
        // Results
        finalScore: 0,
        insights: [],
        
        // Analytics
        showAnalytics: false,
        
        // AI usage tracking
        aiUsage: {
            tokens: 0,
            cost: 0,
            responseTime: 0
        },
        
        // Initialize
        init() {
            console.log('OppaTalent Quiz Generator initialized');
            this.setupEventListeners();
        },
        
        // Setup event listeners
        setupEventListeners() {
            // Keyboard shortcuts
            document.addEventListener('keydown', (e) => {
                if (this.currentStep === 'quiz' && !this.answered) {
                    if (e.key >= '1' && e.key <= '4' && this.currentQuestion?.type === 'multiple_choice') {
                        const index = parseInt(e.key) - 1;
                        if (this.currentQuestion.options[index]) {
                            this.selectAnswer(this.currentQuestion.options[index]);
                        }
                    }
                }
            });
        },
        
        // File handling
        handleDrop(event) {
            this.dragover = false;
            const files = event.dataTransfer.files;
            if (files.length > 0) {
                this.processFile(files[0]);
            }
        },
        
        handleFileSelect(event) {
            const files = event.target.files;
            if (files.length > 0) {
                this.processFile(files[0]);
            }
        },
        
        processFile(file) {
            // Validate file type
            const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
                              'text/plain', 'text/markdown'];
            
            if (!validTypes.includes(file.type) && !file.name.match(/\.(pdf|docx?|txt|md)$/i)) {
                alert('Please upload a PDF, Word document, text file, or Markdown file.');
                return;
            }
            
            // Validate file size (16MB limit)
            if (file.size > 16 * 1024 * 1024) {
                alert('File size must be less than 16MB.');
                return;
            }
            
            this.selectedFile = file;
        },
        
        formatFileSize(bytes) {
            if (!bytes) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        },
        
        // Quiz generation
        async generateQuiz() {
            if (!this.selectedFile) {
                alert('Please select a file first.');
                return;
            }
            
            this.loading = true;
            const startTime = Date.now();
            
            try {
                // Upload document
                const formData = new FormData();
                formData.append('document', this.selectedFile);
                
                const uploadResponse = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                
                if (!uploadResponse.ok) {
                    throw new Error('Failed to upload document');
                }
                
                const uploadData = await uploadResponse.json();
                
                // Generate quiz
                const quizResponse = await fetch('/api/generate-quiz', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-User-ID': this.getUserId()
                    },
                    body: JSON.stringify({
                        content: uploadData.content,
                        num_questions: this.settings.numQuestions,
                        learning_mode: this.settings.mode,
                        difficulty_distribution: this.getBloomDistribution(),
                        include_hints: this.settings.includeHints,
                        include_explanations: this.settings.includeExplanations
                    })
                });
                
                if (!quizResponse.ok) {
                    throw new Error('Failed to generate quiz');
                }
                
                const quizData = await quizResponse.json();
                
                // Update AI usage
                this.aiUsage.tokens = quizData.metadata?.token_usage || 0;
                this.aiUsage.cost = quizData.metadata?.estimated_cost || 0;
                this.aiUsage.responseTime = Date.now() - startTime;
                
                // Set quiz data
                this.quiz = quizData;
                this.currentQuestion = this.quiz.questions[0];
                this.answers = new Array(this.quiz.questions.length).fill(null);
                
                // Start quiz
                this.currentStep = 'quiz';
                this.quizStartTime = Date.now();
                this.questionStartTime = Date.now();
                
            } catch (error) {
                console.error('Error generating quiz:', error);
                alert('Failed to generate quiz. Please try again.');
            } finally {
                this.loading = false;
            }
        },
        
        getBloomDistribution() {
            const dist = {};
            this.bloomLevels.forEach(level => {
                if (level.enabled) {
                    dist[level.name] = level.percentage / 100;
                }
            });
            
            // Normalize
            const total = Object.values(dist).reduce((a, b) => a + b, 0);
            if (total > 0) {
                Object.keys(dist).forEach(key => {
                    dist[key] = dist[key] / total;
                });
            }
            
            return dist;
        },
        
        getUserId() {
            // Get or create user ID for tracking
            let userId = localStorage.getItem('oppa_user_id');
            if (!userId) {
                userId = 'user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
                localStorage.setItem('oppa_user_id', userId);
            }
            return userId;
        },
        
        // Quiz interaction
        selectAnswer(answer) {
            if (this.answered) return;
            
            this.selectedAnswer = answer;
            this.submitAnswer();
        },
        
        submitShortAnswer() {
            if (this.answered || !this.shortAnswer.trim()) return;
            
            this.selectedAnswer = this.shortAnswer;
            this.submitAnswer();
        },
        
        async submitAnswer() {
            this.answered = true;
            const timeSpent = Date.now() - this.questionStartTime;
            
            // For objective questions, check locally
            if (this.currentQuestion.type === 'multiple_choice' || this.currentQuestion.type === 'true_false') {
                this.isCorrect = this.selectedAnswer === this.currentQuestion.correct_answer ||
                               this.selectedAnswer?.startsWith(this.currentQuestion.correct_answer);
            } else {
                // For subjective questions, use AI validation
                try {
                    const response = await fetch('/api/validate-answer', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            question: this.currentQuestion.question,
                            correct_answer: this.currentQuestion.correct_answer,
                            user_answer: this.selectedAnswer,
                            question_type: this.currentQuestion.type
                        })
                    });
                    
                    const validation = await response.json();
                    this.isCorrect = validation.is_correct || validation.score >= 0.7;
                    
                    // Update explanation with AI feedback
                    if (!this.isCorrect && validation.feedback) {
                        this.currentQuestion.explanation = validation.feedback + ' ' + this.currentQuestion.explanation;
                    }
                } catch (error) {
                    console.error('Error validating answer:', error);
                    // Fallback to simple comparison
                    this.isCorrect = this.selectedAnswer.toLowerCase().includes(
                        this.currentQuestion.correct_answer.toLowerCase()
                    );
                }
            }
            
            // Update scoring
            if (this.isCorrect) {
                this.score++;
                this.correctAnswers++;
                this.streak++;
                if (this.streak > this.longestStreak) {
                    this.longestStreak = this.streak;
                }
            } else {
                this.streak = 0;
            }
            
            // Store answer
            this.answers[this.currentQuestionIndex] = {
                question_id: this.currentQuestion.id,
                question: this.currentQuestion.question,
                user_answer: this.selectedAnswer,
                correct_answer: this.currentQuestion.correct_answer,
                is_correct: this.isCorrect,
                time_taken: Math.round(timeSpent / 1000),
                topic: this.currentQuestion.topic,
                bloom_level: this.currentQuestion.bloom_level,
                question_type: this.currentQuestion.type
            };
            
            // Show feedback
            this.showFeedback = true;
        },
        
        getOptionClass(option) {
            if (!this.answered) {
                return 'border-gray-300 hover:border-purple-600 hover:bg-purple-50';
            }
            
            const isSelected = this.selectedAnswer === option || 
                             (this.selectedAnswer?.startsWith && this.selectedAnswer.startsWith(option));
            const isCorrect = option === this.currentQuestion.correct_answer || 
                            option.startsWith(this.currentQuestion.correct_answer);
            
            if (isCorrect) {
                return 'border-green-500 bg-green-50';
            } else if (isSelected && !isCorrect) {
                return 'border-red-500 bg-red-50';
            } else {
                return 'border-gray-300 opacity-50';
            }
        },
        
        // Navigation
        previousQuestion() {
            if (this.currentQuestionIndex > 0) {
                this.currentQuestionIndex--;
                this.loadQuestion();
            }
        },
        
        nextQuestion() {
            if (this.currentQuestionIndex < this.quiz.questions.length - 1) {
                this.currentQuestionIndex++;
                this.loadQuestion();
            }
        },
        
        loadQuestion() {
            this.currentQuestion = this.quiz.questions[this.currentQuestionIndex];
            this.selectedAnswer = this.answers[this.currentQuestionIndex]?.user_answer || null;
            this.shortAnswer = '';
            this.answered = this.answers[this.currentQuestionIndex] !== null;
            this.showFeedback = this.answered;
            this.isCorrect = this.answers[this.currentQuestionIndex]?.is_correct || false;
            this.questionStartTime = Date.now();
        },
        
        // Quiz completion
        async finishQuiz() {
            this.totalTime = Math.round((Date.now() - this.quizStartTime) / 1000);
            this.avgTimePerQuestion = Math.round(this.totalTime / this.quiz.questions.length);
            
            // Submit quiz for grading
            try {
                const response = await fetch('/api/submit-quiz', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-User-ID': this.getUserId()
                    },
                    body: JSON.stringify({
                        quiz_id: this.quiz.id || 'quiz_' + Date.now(),
                        answers: this.answers.filter(a => a !== null),
                        time_taken: this.totalTime
                    })
                });
                
                const report = await response.json();
                
                // Process results
                this.finalScore = report.percentage;
                this.insights = report.insights || [];
                
                // Show results
                this.currentStep = 'results';
                
                // Render charts
                this.$nextTick(() => {
                    this.renderCharts(report);
                });
                
            } catch (error) {
                console.error('Error submitting quiz:', error);
                // Show basic results anyway
                this.finalScore = (this.correctAnswers / this.quiz.questions.length) * 100;
                this.currentStep = 'results';
            }
        },
        
        renderCharts(report) {
            // Topic Performance Chart
            const topicCtx = document.getElementById('topicChart');
            if (topicCtx) {
                new Chart(topicCtx, {
                    type: 'bar',
                    data: {
                        labels: Object.keys(report.topic_scores || {}),
                        datasets: [{
                            label: 'Score (%)',
                            data: Object.values(report.topic_scores || {}).map(s => s * 100),
                            backgroundColor: 'rgba(147, 51, 234, 0.5)',
                            borderColor: 'rgba(147, 51, 234, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        scales: {
                            y: {
                                beginAtZero: true,
                                max: 100
                            }
                        }
                    }
                });
            }
            
            // Bloom's Taxonomy Chart
            const bloomCtx = document.getElementById('bloomChart');
            if (bloomCtx) {
                new Chart(bloomCtx, {
                    type: 'radar',
                    data: {
                        labels: Object.keys(report.bloom_scores || {}),
                        datasets: [{
                            label: 'Performance',
                            data: Object.values(report.bloom_scores || {}).map(s => s * 100),
                            backgroundColor: 'rgba(236, 72, 153, 0.2)',
                            borderColor: 'rgba(236, 72, 153, 1)',
                            pointBackgroundColor: 'rgba(236, 72, 153, 1)',
                            pointBorderColor: '#fff',
                            pointHoverBackgroundColor: '#fff',
                            pointHoverBorderColor: 'rgba(236, 72, 153, 1)'
                        }]
                    },
                    options: {
                        scale: {
                            ticks: {
                                beginAtZero: true,
                                max: 100
                            }
                        }
                    }
                });
            }
        },
        
        // Utility functions
        formatTime(seconds) {
            if (seconds < 60) {
                return `${seconds}s`;
            } else {
                const minutes = Math.floor(seconds / 60);
                const remainingSeconds = seconds % 60;
                return `${minutes}m ${remainingSeconds}s`;
            }
        }
    };
}
