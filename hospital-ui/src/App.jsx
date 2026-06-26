// src/App.jsx
import React, { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, Stethoscope, Database, Upload, X, CheckCircle, Trash2, FileText, Eraser, LogOut } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import Login from './Login'; // Ensure Login.jsx is in the same folder

function App() {
  // ==========================================
  // 1. AUTHENTICATION STATE
  // ==========================================
  const [loggedInUser, setLoggedInUser] = useState({
    username: null,
    userId: null,
    isAuthenticated: false,
  });

  const handleLoginSuccess = (userData) => {
    setLoggedInUser({
  username: userData.username,
  userId: userData.userId,
  firstName: userData.first_name || userData.name || "",  // pull from your Django response
  isAuthenticated: true,
    });
    };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('hospitalChatHistory'); // Clear history on logout
    setMessages([]);
    setLoggedInUser({ username: null, userId: null, isAuthenticated: false });
  };


  // ==========================================
  // 2. CHAT & ADMIN STATE
  // ==========================================
  const [messages, setMessages] = useState(() => {
    const savedChat = localStorage.getItem('hospitalChatHistory');
    return savedChat ? JSON.parse(savedChat) : [];
  });

  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef(null);

  const [showAdmin, setShowAdmin] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');
  const [documents, setDocuments] = useState([]);

  // Auto-save chat history
  useEffect(() => {
    if (loggedInUser.isAuthenticated) {
      localStorage.setItem('hospitalChatHistory', JSON.stringify(messages));
    }
  }, [messages, loggedInUser.isAuthenticated]);

  // Fetch documents when admin modal opens
  useEffect(() => {
    if (showAdmin) {
      fetchDocuments();
    }
  }, [showAdmin]);

  // Auto-scroll chat
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);


  // ==========================================
  // 3. HANDLERS
  // ==========================================
  const clearChat = () => {
    if (window.confirm("Are you sure you want to clear the conversation?")) {
      setMessages([]);
      localStorage.removeItem('hospitalChatHistory');
    }
  };

  const fetchDocuments = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8001/api/admin/documents');
      const data = await response.json();
      setDocuments(data.documents);
    } catch (error) {
      console.error("Failed to fetch documents:", error);
    }
  };

  const handleDelete = async (filename) => {
    if (!window.confirm(`Are you sure you want the AI to forget "${filename}"?`)) return;
    try {
      await fetch(`http://127.0.0.1:8001/api/admin/documents/${filename}`, {
        method: 'DELETE'
      });
      fetchDocuments();
    } catch (error) {
      console.error("Failed to delete:", error);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploadStatus('uploading');
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://127.0.0.1:8001/api/admin/upload', {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        setUploadStatus('success');
        setTimeout(() => {
          setUploadStatus('');
          setShowAdmin(false);
        }, 2000);
      } else {
        setUploadStatus('error');
      }
    } catch (error) {
      console.error("Upload failed:", error);
      setUploadStatus('error');
    }
  };

const sendMessage = async (e) => {
  e.preventDefault();
  if (!input.trim()) return;

  const userMessage = { role: 'user', content: input };
  setMessages(prev => [...prev, userMessage]);
  setInput('');
  setIsTyping(true);

  let aiResponse = { role: 'assistant', content: '' };
  setMessages(prev => [...prev, aiResponse]);

  try {
    // Get the token right before sending!
    const token = localStorage.getItem('access_token') || loggedInUser?.access_token;

    const response = await fetch('http://127.0.0.1:8001/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        "Authorization": `Bearer ${token}` // Injecting token securely
      },
      body: JSON.stringify({
        message: input,
        domain: 'hospital',
        // ✅ Strip JSON for assistant turns before sending history
        history: messages.map(m => {
          if (m.role === 'assistant') {
            try {
              const parsed = JSON.parse(m.content);
              return { role: m.role, content: parsed.summary || m.content };
            } catch {
              return { role: m.role, content: m.content };
            }
          }
          return { role: m.role, content: m.content };
        }),
        patient_username: loggedInUser.username, // Injecting active username
        patient_name: loggedInUser.firstName || loggedInUser.username
      }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let buffer = '';

    // Read the stream chunk by chunk
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep the incomplete last line

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const contentChunk = line.slice(6).trim();

          if (contentChunk === '[DONE]') break;

          // Append the chunk to our response object
          aiResponse.content += contentChunk;

          // Update the UI *inside* the loop for real-time streaming
          setMessages(prev => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1] = { ...aiResponse };
            return newMessages;
          });
        }
      }
    }

  } catch (error) {
    console.error("Error fetching stream:", error);
  } finally {
    setIsTyping(false);
  }
};


  // ==========================================
  // 4. CONDITIONAL RENDERING (Login Gate)
  // ==========================================
  if (!loggedInUser.isAuthenticated) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }


  // ==========================================
  // 5. MAIN CHAT APPLICATION
  // ==========================================
  return (
    <div className="flex flex-col h-screen max-w-3xl mx-auto p-4 md:p-6">

      {/* Header */}
      <header className="flex items-center justify-between mb-8 px-2">
        <div className="flex items-center gap-3">
          <div className="bg-blue-600 p-2 rounded-lg text-white shadow-md">
            <Stethoscope size={24} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-800">CareFirst Assistant</h1>
            <p className="text-sm text-slate-500">
              Welcome, <span className="font-semibold text-blue-600">{loggedInUser.username}</span>
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <button
              onClick={clearChat}
              className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
              title="Clear Chat History"
            >
              <Eraser size={20} />
            </button>
          )}
          <button
            onClick={() => setShowAdmin(true)}
            className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
            title="Update AI Brain"
          >
            <Database size={20} />
          </button>
          <button
            onClick={handleLogout}
            className="p-2 text-slate-400 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors ml-2"
            title="Log Out"
          >
            <LogOut size={20} />
          </button>
        </div>
      </header>

      {/* Admin Modal Overlay */}
      <AnimatePresence>
        {showAdmin && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="absolute inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4"
          >
            <motion.div
              initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }}
              className="bg-white w-full max-w-md rounded-2xl shadow-2xl overflow-hidden relative flex flex-col max-h-[85vh]"
            >
              <div className="p-6 pb-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                <div>
                  <h2 className="text-xl font-bold text-slate-800">Memory Manager</h2>
                  <p className="text-xs text-slate-500 mt-1">Manage the AI's active knowledge base</p>
                </div>
                <button onClick={() => setShowAdmin(false)} className="text-slate-400 hover:text-slate-700 bg-white p-2 rounded-full shadow-sm">
                  <X size={20} />
                </button>
              </div>

              <div className="p-6 overflow-y-auto">
                <div className="border-2 border-dashed border-slate-200 rounded-xl p-6 flex flex-col items-center justify-center bg-slate-50 hover:bg-blue-50 transition-colors relative mb-8">
                  {uploadStatus === '' && (
                    <>
                      <Upload className="text-blue-500 mb-2" size={28} />
                      <span className="text-sm font-medium text-slate-700">Upload new protocol (PDF)</span>
                      <input type="file" accept=".pdf" onChange={(e) => { handleFileUpload(e); setTimeout(fetchDocuments, 2000); }} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
                    </>
                  )}
                  {uploadStatus === 'uploading' && <span className="text-sm font-medium text-blue-600 animate-pulse">Injecting into AI Brain...</span>}
                  {uploadStatus === 'success' && <span className="text-sm font-medium text-green-600">Knowledge updated!</span>}
                  {uploadStatus === 'error' && <span className="text-sm font-medium text-red-600">Upload failed.</span>}
                </div>

                <h3 className="text-sm font-bold text-slate-800 mb-3 uppercase tracking-wider">Active Documents ({documents.length})</h3>
                <div className="space-y-2">
                  {documents.length === 0 ? (
                    <p className="text-sm text-slate-500 italic text-center py-4">No documents in memory.</p>
                  ) : (
                    documents.map((doc, idx) => (
                      <div key={idx} className="flex items-center justify-between p-3 bg-white border border-slate-200 rounded-lg hover:border-blue-300 transition-colors group">
                        <div className="flex items-center gap-3 overflow-hidden">
                          <FileText className="text-slate-400 shrink-0" size={18} />
                          <span className="text-sm font-medium text-slate-700 truncate">{doc}</span>
                        </div>
                        <button
                          onClick={() => handleDelete(doc)}
                          className="text-slate-300 hover:text-red-500 p-1.5 rounded-md hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100"
                          title="Delete from memory"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto space-y-6 px-2 mb-4 scrollbar-hide">
          <AnimatePresence>
            {messages.map((msg, index) => (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                key={index}
                className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role !== 'user' && (
                  <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 shrink-0">
                    <Bot size={18} />
                  </div>
                )}

                <div className={`max-w-[85%] p-4 rounded-2xl shadow-sm ${
                  msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-tr-none'
                  : 'bg-white border border-slate-100 rounded-tl-none text-slate-700'
                }`}>
                  {msg.role === 'user' ? (
                    msg.content || (isTyping && "...")
                  ) : (
                    <div className="text-sm">
                      {(() => {
                        if (isTyping && !msg.content) return "...";
                        try {
                          const data = JSON.parse(msg.content);
                          return (
                            <div>
                                <div className="mb-3 text-slate-700 leading-relaxed">
                                  <ReactMarkdown>{data.summary}</ReactMarkdown>
                                </div>

                              {data.items && data.items.length > 0 && (
                                <ul className="list-disc pl-5 space-y-2 marker:text-blue-500 mb-3">
                                  {data.items.map((item, idx) => (
                                    <li key={idx} className="text-slate-700 leading-relaxed">
                                      <ReactMarkdown>{item}</ReactMarkdown>
                                    </li>
                                  ))}
                                </ul>
                              )}

                              {data.action && data.action.type === "REQUIRE_AUTH" && (
                              <div className="mt-4 p-4 bg-slate-50 border border-slate-200 rounded-lg shadow-inner">
                                <div className="flex items-center gap-2 mb-3">
                                  <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
                                  </svg>
                                  <span className="font-semibold text-slate-800">Secure Booking:</span>
                                  <span className="text-blue-600 font-medium">
                                  Dr. {data.action.target.replace(/\*\*/g, '').charAt(0).toUpperCase() + data.action.target.replace(/\*\*/g, '').slice(1)}
                                </span>
                                </div>

                                <input
                                  type="password"
                                  placeholder="Enter 6-Digit Patient Key..."
                                  className="patient-auth-key-input w-full text-sm p-2 border border-slate-300 rounded mb-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                                <button
                                  onClick={async (e) => {
                                // 1. CACHE THE DOM ELEMENTS BEFORE THE AWAIT (Fixes the null crash)
                                const button = e.currentTarget;
                                const container = button.parentElement;

                                // Grab the input value based on your specific DOM structure
                                // (Adjust the selector if your input has a different class/id)
                                const inputEl = container.querySelector('input[type="password"]');
                                const secret_key = inputEl ? inputEl.value : "";

                                if (!secret_key) {
                                    alert("Please enter your 6-digit key.");
                                    return;
                                }

                                // 2. INSTANTLY LOCK THE UI AND SHOW LOADING SPINNER
                                button.disabled = true;
                                const originalButtonText = button.innerHTML;
                                button.innerHTML = `
                                  <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline-block" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                  </svg>
                                  Verifying...
                                `;
                                button.classList.add('opacity-70', 'cursor-not-allowed');

                                // 3. MAKE THE API CALL
                                try {
                                    // 🛠️ GET YOUR TOKEN HERE (Adjust 'access_token' if your key is named differently!)
                                    const myToken = localStorage.getItem('access_token');

                                    const res = await fetch('http://127.0.0.1:8000/api/bot/verify-book/', {
                                        method: 'POST',
                                        headers: {
                                            'Content-Type': 'application/json',
                                            "Authorization": `Bearer ${myToken}` // 🛠️ Use the variable we just defined
                                        },
                                        body: JSON.stringify({
                                            patient_username: loggedInUser.username,
                                            doctor_name: data.action.target,
                                            secret_key: secret_key,
                                            scheduled_time: data.action.scheduled_time
                                        }),
                                    });

                                    const result = await res.json();

                                    // 4. HANDLE THE OUTCOME
                                    if (res.status === 201 || res.status === 200) {
                                        // Success! Melt the container into the green banner
                                        container.innerHTML = `
                                          <div class="flex items-center gap-3 p-3 bg-green-50 border border-green-200 rounded-lg transition-all duration-500 ease-in-out">
                                            <svg class="w-5 h-5 text-green-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                                            </svg>
                                            <span class="font-medium text-green-800 text-sm">Appointment request submitted successfully!</span>
                                          </div>
                                        `;
                                    } else {
                                        // Failed (e.g. 409 Conflict or wrong password). Unlock the button so they can try again.
                                        button.disabled = false;
                                        button.innerHTML = originalButtonText;
                                        button.classList.remove('opacity-70', 'cursor-not-allowed');
                                        alert(`Verification failed: ${result.error || 'Invalid key'}`);
                                    }
                                } catch (error) {
                                    console.error("Network Error:", error);
                                    button.disabled = false;
                                    button.innerHTML = originalButtonText;
                                    button.classList.remove('opacity-70', 'cursor-not-allowed');
                                    alert("A network error occurred while verifying.");
                                }
                            }}
                                  className="w-full bg-slate-800 text-white font-medium text-sm py-2 rounded hover:bg-slate-700 transition-colors"
                                >
                                  Verify & Confirm Appointment
                                </button>
                              </div>
                            )}

                            </div>
                          );
                        } catch (e) {
                          return <div className="whitespace-pre-wrap">{msg.content}</div>;
                        }
                      })()}
                    </div>
                  )}
                </div>

                {msg.role === 'user' && (
                  <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 shrink-0">
                    <User size={18} />
                  </div>
                )}

              </motion.div>
            ))}
          </AnimatePresence>
          <div ref={scrollRef} />
        </div>

      {/* Input Area */}
      <form onSubmit={sendMessage} className="relative group">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about medications or symptoms..."
          className="w-full bg-white border border-slate-200 rounded-2xl px-6 py-4 pr-16 shadow-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
        />
        <button
          type="submit"
          className="absolute right-3 top-1/2 -translate-y-1/2 bg-blue-600 text-white p-2 rounded-xl hover:bg-blue-700 transition-colors"
        >
          <Send size={20} />
        </button>
      </form>
    </div>
  );
}

export default App;