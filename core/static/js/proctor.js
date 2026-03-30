let videoStream;
let audioContext;
let analyser;
let microphone;
let warningCount = 0;
const MAX_WARNINGS = 3;
const AUDIO_THRESHOLD = 0.2; 
let lastAudioViolationTime = 0;
const AUDIO_VIOLATION_COOLDOWN = 10000; 

// Timer logic
let startTime;
let timerInterval;

function startTimer() {
    startTime = Date.now();
    timerInterval = setInterval(updateTimer, 1000);
}

function updateTimer() {
    const now = Date.now();
    const diff = Math.floor((now - startTime) / 1000);
    
    const hours = Math.floor(diff / 3600);
    const minutes = Math.floor((diff % 3600) / 60);
    const seconds = diff % 60;
    
    const formattedTime = 
        String(hours).padStart(2, '0') + ':' + 
        String(minutes).padStart(2, '0') + ':' + 
        String(seconds).padStart(2, '0');
        
    const timerDisplay = document.getElementById('exam-timer');
    if (timerDisplay) {
        timerDisplay.innerText = formattedTime;
    }
    
    const timeInput = document.getElementById('time_taken_input');
    if (timeInput) {
        timeInput.value = formattedTime;
    }
}

// Tab Switching / Window Focus detection
document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
        const examId = getExamId();
        if (examId) {
            reportViolationToServer("Tab/Window Switched", examId);
        }
    }
});

window.addEventListener("blur", () => {
    const examId = getExamId();
    if (examId) {
        reportViolationToServer("Window Lost Focus", examId);
    }
});

async function startCamera() {
    const videoElement = document.getElementById('webcam');
    if (!videoElement) return;
    
    try {
        videoStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        videoElement.srcObject = videoStream;
        console.log("Camera and Microphone started");

        setupAudioMonitoring(videoStream);
        startMonitoring();
    } catch (err) {
        alert("Camera and Microphone access are required for this exam. Please allow access.");
        console.error("Media error:", err);
    }
}

function setupAudioMonitoring(stream) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioContext.createAnalyser();
    microphone = audioContext.createMediaStreamSource(stream);
    microphone.connect(analyser);
    analyser.fftSize = 256;

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function checkVolume() {
        analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
            sum += dataArray[i];
        }
        let average = sum / bufferLength;
        let normalizedVolume = average / 255;

        if (normalizedVolume > AUDIO_THRESHOLD) {
            handleAudioViolation();
        }

        requestAnimationFrame(checkVolume);
    }

    checkVolume();
}

function handleAudioViolation() {
    const now = Date.now();
    if (now - lastAudioViolationTime > AUDIO_VIOLATION_COOLDOWN) {
        lastAudioViolationTime = now;
        const examId = getExamId();
        if (examId) {
            reportViolationToServer("Noise Detected", examId);
        }
    }
}

function updateFraudScoreUI(count) {
    const score = Math.min(100, count * 20); // 20% per violation
    
    const bar = document.getElementById('fraud-score-bar');
    const text = document.getElementById('fraud-score-text');
    
    if (bar && text) {
        bar.style.width = `${score}%`;
        text.innerText = `${score}%`;
        
        if (score > 60) {
            bar.className = "h-2.5 rounded-full transition-all duration-500 bg-red-500";
            text.className = "font-bold text-red-500";
        } else if (score > 20) {
            bar.className = "h-2.5 rounded-full transition-all duration-500 bg-yellow-500";
            text.className = "font-bold text-yellow-500";
        }
    }
}

function handleViolation(data) {
    const type = data.violation_type || "Violation";
    const count = data.violation_count || (warningCount + 1);
    const terminated = data.terminated || false;

    warningCount = count;
    updateFraudScoreUI(warningCount);

    const warningArea = document.getElementById('warning-area');
    const warningText = document.getElementById('warning-text');
    if (warningArea && warningText) {
        warningText.innerText = `${type} detected! (${warningCount}/${MAX_WARNINGS} violations)`;
        warningArea.classList.remove('hidden');
    }

    if (terminated || warningCount >= MAX_WARNINGS) {
        alert("Too many violations detected. Exam will be auto-submitted and terminated.");
        
        const statusInput = document.getElementById('exam_status_input');
        if (statusInput) statusInput.value = 'Terminated';
        
        const form = document.getElementById('exam-form');
        if (form) {
            form.submit();
        }
    }
}

function reportViolationToServer(type, examId) {
    const formData = new URLSearchParams();
    formData.append('violation_type', type);
    formData.append('exam_id', examId);

    fetch('/report_violation/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: formData.toString()
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' || data.violation_count !== undefined) {
                handleViolation(data);
            }
        })
        .catch(err => console.error("Violation reporting error:", err));
}

function getExamId() {
    const pathParts = window.location.pathname.split('/');
    const examIndex = pathParts.indexOf('exam');
    if (examIndex !== -1 && pathParts[examIndex + 1]) {
        return pathParts[examIndex + 1];
    }
    return null;
}

function startMonitoring() {
    setInterval(captureAndSendFrame, 3000); // Check visual every 3 seconds for scalability balance
}

let isSendingFrame = false;

function captureAndSendFrame() {
    if(isSendingFrame) return; // Wait for previous frame to finish processing to prevent overload
    isSendingFrame = true;

    const videoElement = document.getElementById('webcam');
    if (!videoElement || !videoElement.videoWidth) {
        isSendingFrame = false;
        return;
    }

    const canvas = document.createElement('canvas');
    canvas.width = videoElement.videoWidth;
    canvas.height = videoElement.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);

    const dataURL = canvas.toDataURL('image/jpeg', 0.6); // Compress slightly
    const examId = getExamId();

    const body = new URLSearchParams();
    body.append('image', dataURL);
    if (examId) body.append('exam_id', examId);

    fetch('/detect/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: body.toString()
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'violation' || (data.violation_count !== undefined && data.violation_count > warningCount)) {
                handleViolation(data);
            } else if (data.violation_count !== undefined) {
                warningCount = data.violation_count;
                updateFraudScoreUI(warningCount);
            }
        })
        .catch(err => console.error("Proctoring error:", err))
        .finally(() => {
            isSendingFrame = false;
        });
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

document.addEventListener('DOMContentLoaded', () => {
    // Only run if we are on the exam portal page
    if (document.getElementById('webcam')) {
        startTimer();
        startCamera();
    }
});
