import React, { useState, useEffect, useCallback } from 'react';
import Row from 'react-bootstrap/Row';
import Col from 'react-bootstrap/Col';
import Button from 'react-bootstrap/Button';
import Modal from 'react-bootstrap/Modal';
import Form from 'react-bootstrap/Form';
import Alert from 'react-bootstrap/Alert'; // Added Alert import
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faPlus, faMicrophone, faStop, faPencilAlt, faTrashAlt, faCheck } from '@fortawesome/free-solid-svg-icons';
import './App.css'; // Your custom styles

const API_BASE_URL = 'http://localhost:8000/api'; // Adjust if your API prefix is different

// Define interfaces for your data structures
interface Task {
  id: number;
  description: string;
  status: 'pending' | 'inprogress' | 'done';
  // Add other fields from your Pydantic model if needed, e.g., created_at, updated_at
}


interface TaskManagerVersionInfo {
  id: number;
  version_number: number;
  created_at: string; // Assuming ISO string from backend
}

interface ModelInfo {
  name: string;
  size_mb: number;
  is_downloaded: boolean;
}

const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
let recognition: any = null;

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = true; // Keep listening even after a pause
  recognition.interimResults = true; // Get results as they are being spoken
  recognition.lang = 'en-US'; // Set language
} else {
  console.warn('Speech Recognition API not supported in this browser.');
}

function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [currentTask, setCurrentTask] = useState<Partial<Task> | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState('Your transcription will appear here...');
  const [selectedModel, setSelectedModel] = useState('small.en'); // Default to small.en
  const [modelStatuses, setModelStatuses] = useState<{ [key: string]: ModelInfo }>({});
  const [downloadingModel, setDownloadingModel] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [availableVersions, setAvailableVersions] = useState<TaskManagerVersionInfo[]>([]);
  const [selectedVersionNumber, setSelectedVersionNumber] = useState<number | 'latest'>('latest');
  const [isLoadingTasks, setIsLoadingTasks] = useState(false);
  const [isLoadingVersions, setIsLoadingVersions] = useState(false);


  // --- API Interaction ---
  const fetchVersions = useCallback(async () => {
    setIsLoadingVersions(true);
    setApiError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/versions`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status} - Failed to fetch versions`);
      }
      const data: TaskManagerVersionInfo[] = await response.json();
      setAvailableVersions(data);
      if (data.length > 0 && selectedVersionNumber === 'latest') {
        // If 'latest' was selected and versions are available, point to the newest one by number
        // Assuming versions are sorted descending by version_number from the API
        // setSelectedVersionNumber(data[0].version_number);
      } else if (data.length === 0) {
        setSelectedVersionNumber('latest'); // Fallback if no versions exist
      }
      return data; // Return data for chaining if needed
    } catch (error) {
      console.error('Failed to fetch versions:', error);
      setApiError(String(error));
      setAvailableVersions([]);
      return [];
    } finally {
      setIsLoadingVersions(false);
    }
  }, [selectedVersionNumber]);

  const fetchTasks = useCallback(async (versionToFetch: number | 'latest' = 'latest') => {
    setIsLoadingTasks(true);
    setApiError(null);
    try {
      let url = `${API_BASE_URL}/tasks`;
      if (typeof versionToFetch === 'number') {
        url = `${API_BASE_URL}/versions/${versionToFetch}/tasks`;
      }
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status} - Failed to fetch tasks for version ${versionToFetch}`);
      }
      const data: Task[] = await response.json();
      setTasks(data);
    } catch (error) {
      console.error(`Failed to fetch tasks for version ${versionToFetch}:`, error);
      setApiError(String(error)); // Use String(error) for potentially better error messages
      setTasks([]); // Clear tasks on error
    } finally {
      setIsLoadingTasks(false);
    }
  }, []);

  const fetchAllModelStatuses = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/models`);
      if (!response.ok) throw new Error('Failed to fetch model statuses');
      const data: ModelInfo[] = await response.json();
      const statuses = data.reduce((acc, model) => {
        acc[model.name] = model;
        return acc;
      }, {} as { [key: string]: ModelInfo });
      setModelStatuses(statuses);
    } catch (error) {
      console.error('Failed to fetch model statuses:', error);
      setApiError('Failed to load model statuses. Please check the backend.');
    }
  }, []);

  useEffect(() => {
    // Initial data load sequence
    const loadInitialData = async () => {
      await fetchVersions(); // Fetches and sets availableVersions
      // fetchTasks will use selectedVersionNumber (initially 'latest').
      // If 'latest', /api/tasks is called, which returns the true latest.
      // If a number (e.g., from URL persistence or future feature), it fetches that version.
      await fetchTasks(selectedVersionNumber); 
      await fetchAllModelStatuses();
    };

    loadInitialData();
    // selectedVersionNumber is kept in dependencies because if it changes (e.g. from a future URL param),
    // this effect should re-run to load the correct initial data.
    // fetchVersions, fetchTasks, fetchAllModelStatuses are stable due to useCallback.
  }, [fetchVersions, fetchTasks, fetchAllModelStatuses, selectedVersionNumber]); // Add selectedVersionNumber to re-fetch if it changes programmatically outside dropdown

  // Cleanup recognition on component unmount
  useEffect(() => {
    return () => {
      if (recognition) {
        recognition.stop();
      }
    };
  }, []);

  // --- Event Handlers --- 
  const handleCreateTaskClick = () => {
    // Removed read-only check
    setCurrentTask({ description: '', status: 'pending' }); // Initialize for new task
    setShowTaskModal(true);
  };

  const handleEditTask = (task: Task) => {
    // Removed read-only check
    setCurrentTask(task);
    setShowTaskModal(true);
  };

  const handleDeleteTask = async (taskId: number) => {
    // Removed read-only check
    if (!window.confirm(`Are you sure you want to delete TASK-${taskId}?`)) {
      return;
    }
    try {
      setApiError(null);
      let url = `${API_BASE_URL}/tasks/${taskId}`;
      if (typeof selectedVersionNumber === 'number') {
        url += `?base_version_number=${selectedVersionNumber}`;
      }
      const response = await fetch(url, { method: 'DELETE' });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: `HTTP error! status: ${response.status}` }));
        throw new Error(errorData.detail || 'Failed to delete task');
      }
      // Task deleted successfully
      setShowTaskModal(false); // Close modal if open for this task
      await fetchVersions();
      setSelectedVersionNumber('latest');
      await fetchTasks('latest');
    } catch (error) {
      console.error('Failed to delete task:', error);
      setApiError(String(error));
    }
  };

  const handleSaveTask = async () => {
    if (!currentTask || !currentTask.description || !currentTask.status) {
      setApiError('Task description and status are required.');
      return;
    }
    // Removed read-only check

    const method = currentTask.id ? 'PUT' : 'POST';
    const url = currentTask.id ? `${API_BASE_URL}/tasks/${currentTask.id}` : `${API_BASE_URL}/tasks`;

    const requestBody: any = {
      description: currentTask.description,
      status: currentTask.status,
    };

    if (typeof selectedVersionNumber === 'number') {
      requestBody.base_version_number = selectedVersionNumber;
    }

    try {
      setApiError(null);
      const response = await fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: `HTTP error! status: ${response.status}` }));
        throw new Error(errorData.detail || `Failed to ${currentTask.id ? 'update' : 'create'} task`);
      }

      // Task saved successfully
      setShowTaskModal(false);
      await fetchVersions();
      setSelectedVersionNumber('latest'); // Go to the new latest version
      await fetchTasks('latest'); // Fetch tasks for the new latest version

    } catch (error) {
      console.error(`Failed to ${currentTask.id ? 'update' : 'create'} task:`, error);
      setApiError(String(error));
    }
  };

  const handleRecordClick = () => {
    if (!recognition) {
      setTranscript('Speech recognition is not supported in your browser.');
      return;
    }

    if (isRecording) {
      recognition.stop();
      setIsRecording(false);
      if (transcript && transcript !== 'Listening...' && transcript !== 'Your transcription will appear here...' && !transcript.startsWith('Speech recognition error')) {
        processVoiceCommand(transcript);
      } else {
        console.log('No valid final transcript to process or recording was stopped prematurely.');
      }
    } else {
      setTranscript('Listening...'); // Clear previous transcript or set to listening
      try {
        recognition.start();
        setIsRecording(true);

        recognition.onresult = (event: any) => {
          let interimTranscript = '';
          let finalTranscript = '';
          for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
              finalTranscript += event.results[i][0].transcript;
            } else {
              interimTranscript += event.results[i][0].transcript;
            }
          }
          // Update transcript state with the latest, preferring final if available
          setTranscript(finalTranscript || interimTranscript);
        };

        recognition.onerror = (event: any) => {
          console.error('Speech recognition error', event.error);
          setTranscript(`Speech recognition error: ${event.error}`);
          setIsRecording(false);
        };

        recognition.onend = () => {
          // Only set isRecording to false if it wasn't manually stopped
          // This handles cases where recognition stops unexpectedly
          if (isRecording && recognition) { // Check if recognition still exists
             // recognition.stop(); // ensure it's stopped if it ended prematurely
          }
          // setIsRecording(false); // Let the button click handle this for explicit stops
        };

      } catch (error) {
        console.error('Error starting speech recognition:', error);
        setTranscript('Could not start voice recognition.');
        setIsRecording(false);
      }
    }
  };

  const handleVersionChange = async (event: React.ChangeEvent<HTMLSelectElement>) => {
    const newVersionSelection = event.target.value;
    if (newVersionSelection === 'latest') {
      setSelectedVersionNumber('latest');
      // Fetch tasks for 'latest' which now points to the /api/tasks endpoint
      await fetchTasks('latest'); 
    } else {
      const versionNum = parseInt(newVersionSelection, 10);
      setSelectedVersionNumber(versionNum);
      await fetchTasks(versionNum);
    }
  };

  const handleModelChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    setSelectedModel(event.target.value);
  };

  const processVoiceCommand = async (commandText: string) => {
    // Removed read-only check
    setTranscript(`Processing: "${commandText}"...`); // Update transcript to show processing

    const requestBody: any = {
      text: commandText,
      model: selectedModel,
      current_tasks: tasks, // Backend uses this if base_version_number is not set
    };

    if (typeof selectedVersionNumber === 'number') {
      requestBody.base_version_number = selectedVersionNumber;
    }

    try {
      setApiError(null);
      const response = await fetch(`${API_BASE_URL}/process_voice_command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody), 
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: `HTTP error! status: ${response.status}` }));
        throw new Error(errorData.detail || 'Failed to process voice command');
      }

      const result = await response.json();
      // The backend's voice command processing now directly updates tasks and creates a new version.
      // So, we just need to refresh our view to the latest.
      setTranscript(`LLM: ${result.message || 'Command processed.'}`); // Display LLM response message
      
      await fetchVersions();
      setSelectedVersionNumber('latest');
      await fetchTasks('latest');

    } catch (error) {
      console.error('Failed to process voice command:', error);
      const errorMessage = String(error);
      setApiError(errorMessage);
      setTranscript(`Error: ${errorMessage}`);
    }
  };

  const handleDownloadModel = async () => {
    if (!selectedModel) {
      alert('Please select a model first.');
      return;
    }
    setDownloadingModel(selectedModel);
    try {
      const response = await fetch(`${API_BASE_URL}/download_model?model=${selectedModel}`, {
        method: 'GET',
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Failed to download ${selectedModel}`);
      }
      alert(`${selectedModel} downloaded successfully!`);
    } catch (error) {
      console.error('Failed to download model:', error);
      alert(`Failed to download ${selectedModel}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setDownloadingModel(null);
      fetchAllModelStatuses();
    }
  };
  
  // --- Drag and Drop Handlers ---
  const handleDragStart = (e: React.DragEvent<HTMLDivElement>, task: Task) => {
    // Set the drag data to be the task ID
    e.dataTransfer.setData('text/plain', task.id.toString());
    // Add a class to style the dragged element
    e.currentTarget.classList.add('dragging');
    // Set effectAllowed to move to indicate we're moving the task
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragEnd = (e: React.DragEvent<HTMLDivElement>) => {
    // Remove the dragging class
    e.currentTarget.classList.remove('dragging');
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    // Prevent default to allow drop
    e.preventDefault();
    // Set dropEffect to move to indicate we're moving the task
    e.dataTransfer.dropEffect = 'move';
    // Add drag-over class for visual feedback
    e.currentTarget.classList.add('drag-over');
  };
  
  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    // Remove drag-over class when dragging out of the element
    e.currentTarget.classList.remove('drag-over');
  };

  const handleDrop = async (e: React.DragEvent<HTMLDivElement>, newStatus: 'pending' | 'inprogress' | 'done') => {
    e.preventDefault();
    
    // Remove the drag-over class
    e.currentTarget.classList.remove('drag-over');
    
    // Get the task ID from dataTransfer
    const taskId = parseInt(e.dataTransfer.getData('text/plain'), 10);
    const task = tasks.find(t => t.id === taskId);
    
    if (!task) return;
    if (task.status === newStatus) return; // No change needed
    
    try {
      // Create task update payload
      const updatePayload = {
        status: newStatus,
        description: task.description,
        base_version_number: typeof selectedVersionNumber === 'number' ? selectedVersionNumber : undefined
      };
      
      setApiError(null);
      const response = await fetch(`${API_BASE_URL}/tasks/${taskId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatePayload),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Failed to update task: ${response.statusText}`);
      }
      
      // Update was successful, refresh the task list to show the latest version
      await fetchVersions();
      setSelectedVersionNumber('latest');
      await fetchTasks('latest');
    } catch (error) {
      console.error('Error updating task status:', error);
      setApiError(`Error updating task status: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  // --- Render Logic --- 
  const renderTaskCard = (task: Task) => (
    <div 
      className="task" 
      data-task-id={task.id} 
      data-status={task.status}
      draggable="true"
      onDragStart={(e) => handleDragStart(e, task)}
      onDragEnd={handleDragEnd}
    >
      <div className="task-header">
        <span className="task-id-display">TASK-{task.id}</span>
      </div>
      <div className="task-description-text">{task.description}</div>
      <div className="task-actions">
        <Button variant="link" size="sm" title="Edit Task" onClick={() => handleEditTask(task)} className="p-0 me-2">
          <FontAwesomeIcon icon={faPencilAlt} />
        </Button>
        <Button variant="link" size="sm" title="Delete Task" onClick={() => handleDeleteTask(task.id)} className="p-0 text-danger">
          <FontAwesomeIcon icon={faTrashAlt} />
        </Button>
      </div>
    </div>
  );

  return (
    <div className="app-container">
      {/* Task Edit/Create Modal */}
      <Modal show={showTaskModal} onHide={() => setShowTaskModal(false)} size="lg" centered>
        <Modal.Header closeButton>
          <Modal.Title>{currentTask?.id ? `Edit Task (TASK-${currentTask.id})` : 'Create New Task'}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form>
            {currentTask?.id && ( // Show Task ID only for existing tasks
              <Form.Group className="mb-3">
                <Form.Label>Task ID</Form.Label>
                <Form.Control type="text" readOnly disabled value={`TASK-${currentTask.id}`} />
              </Form.Group>
            )}
            <Form.Group className="mb-3">
              <Form.Label htmlFor="modalTaskDescription">Description</Form.Label>
              <Form.Control
                as="textarea"
                rows={4}
                id="modalTaskDescription"
                required
                value={currentTask?.description || ''}
                onChange={(e) => setCurrentTask(prev => ({ ...prev, description: e.target.value }))}
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label htmlFor="modalTaskStatus">Status</Form.Label>
              <Form.Select
                id="modalTaskStatus"
                required
                value={currentTask?.status || 'pending'}
                onChange={(e) => setCurrentTask(prev => ({ ...prev, status: e.target.value as Task['status'] }))}
              >
                <option value="pending">Pending</option>
                <option value="inprogress">In Progress</option>
                <option value="done">Done</option>
              </Form.Select>
            </Form.Group>
          </Form>
        </Modal.Body>
        <Modal.Footer>
          {currentTask?.id && (
            <Button variant="outline-danger" className="me-auto" onClick={() => handleDeleteTask(currentTask.id!)}>
              <FontAwesomeIcon icon={faTrashAlt} className="me-1" /> Delete Task
            </Button>
          )}
          <Button variant="secondary" onClick={() => setShowTaskModal(false)}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSaveTask} disabled={!currentTask?.description || !currentTask?.status}>
            <FontAwesomeIcon icon={faCheck} /> {currentTask?.id ? 'Save Changes' : 'Create Task'}
          </Button>
        </Modal.Footer>
      </Modal>

    {/* Header */}
    <header className="app-header mb-4">
      <Row className="justify-content-between align-items-center">
        <Col>
          <div className="logo-text">Tasky<span>!!</span></div>
        </Col>
        <Col md="auto" className="d-flex align-items-center">
          <Form.Label htmlFor="versionSelect" className="me-2 header-form-label">Version:</Form.Label>
          {isLoadingVersions ? (
            <span className="me-2 text-muted small">Loading versions...</span>
          ) : (
            <Form.Select id="versionSelect" value={selectedVersionNumber} onChange={handleVersionChange} size="sm" style={{ width: 'auto', minWidth: '180px' }} className="me-3" aria-label="Select task version">
              <option value="latest">Latest Version</option>
              {availableVersions.map(v => (
                <option key={v.id} value={v.version_number}>
                  Version {v.version_number} ({new Date(v.created_at).toLocaleString()})
                </option>
              ))}
            </Form.Select>
          )}
        </Col>
        <Col md="auto" className="d-flex align-items-center ms-auto me-3" id="model-selection-header-area">
          <Form.Label htmlFor="modelSelect" className="me-2 header-form-label">Voice model:</Form.Label> {/* Visually hidden but good for accessibility */}
          <Form.Select id="modelSelect" value={selectedModel} onChange={handleModelChange} size="sm" style={{ width: 'auto', minWidth: '120px' }} className="me-2">
            <option value="small.en">Small.en</option>
            <option value="medium.en">Medium.en</option>
          </Form.Select>

          {/* Model Status & Download Button Logic */}
          {(() => {
            const currentStatus = modelStatuses[selectedModel];
            if (downloadingModel === selectedModel) {
              return (
                <Button variant="secondary" size="sm" disabled style={{ whiteSpace: 'nowrap' }}>
                  Downloading...
                </Button>
              );
            }
            if (currentStatus) {
              return currentStatus.is_downloaded ? (
                <Button variant="success" size="sm" disabled style={{ whiteSpace: 'nowrap' }}>
                  <FontAwesomeIcon icon={faCheck} className="me-1" />
                  Downloaded
                </Button>
              ) : (
                <Button variant="outline-primary" size="sm" onClick={handleDownloadModel} style={{ whiteSpace: 'nowrap' }}>
                  Download ({currentStatus.size_mb}MB)
                </Button>
              );
            }
            return <span className="me-2 text-muted" style={{ fontSize: '0.8rem' }}>Loading...</span>;
          })()}
        </Col>
        <Col xs="auto">
          <Button variant="primary" onClick={handleCreateTaskClick} className="rounded-pill" title="Create a new task">
            <FontAwesomeIcon icon={faPlus} className="me-2" /> Create Task
          </Button>
        </Col>
      </Row>
    </header>

    {/* Controls Area: Transcript ONLY */} 
    <div className="controls-area mb-4">
      <div id="transcript">
        {transcript}
      </div>
    </div>

    {/* API Error Display */}
    {apiError && (
      <Alert variant="danger" onClose={() => setApiError(null)} dismissible>
        {apiError}
      </Alert>
    )}

    {/* Task Columns Loading State */} 
    {isLoadingTasks && (
      <Row className="justify-content-center my-4">
        <Col xs="auto">
          <Alert variant="info">Loading tasks for selected version...</Alert>
        </Col>
      </Row>
    )}

    {/* Task Columns */}
    <Row id="columns" className="flex-grow-1">
      {['pending', 'inprogress', 'done'].map(statusKey => {
        // Calculate task count for this column
        const taskCount = tasks.filter(task => task.status === statusKey).length;
        const title = statusKey === 'inprogress' ? 'In Progress' : statusKey.charAt(0).toUpperCase() + statusKey.slice(1);
        
        return (
          <Col key={statusKey} id={statusKey} className="column">
            <h2 data-count={taskCount}>{title}</h2>
            <div 
              className="column-content" 
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, statusKey as 'pending' | 'inprogress' | 'done')}
            >
              {taskCount === 0 && (
                <p className="column-empty-message text-muted-light small fst-italic mt-2">No tasks yet.</p>
              )}
              {tasks.filter(task => task.status === statusKey).map(task => renderTaskCard(task))}
            </div>
          </Col>
        );
      })}
    </Row>

    {/* Microphone Button */}
    <div className="mic-button-container">
      <Button id="record" onClick={handleRecordClick} variant={isRecording ? 'danger' : 'success'} disabled={!recognition} title={isRecording ? 'Stop Recording' : 'Start Recording'}>
        <FontAwesomeIcon icon={isRecording ? faStop : faMicrophone} />
      </Button>
    </div>

  </div>
);
}

export default App;
