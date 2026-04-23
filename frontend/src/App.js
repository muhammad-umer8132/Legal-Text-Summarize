import React, { useState, useCallback, useEffect } from 'react';
import { Upload, FileText, Download, Loader2, CheckCircle, AlertCircle, X, Sparkles, Brain, Scale, FileCheck, Zap, ArrowRight, Globe } from 'lucide-react';
import axios from 'axios';
import './App.css';

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

function App() {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [taskId, setTaskId] = useState(null);
  const [status, setStatus] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [downloadUrl, setDownloadUrl] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (analyzing) {
      const interval = setInterval(() => {
        setProgress(prev => (prev >= 90 ? 90 : prev + 10));
      }, 1000);
      return () => clearInterval(interval);
    } else {
      setProgress(0);
    }
  }, [analyzing]);

  const handleFileSelect = (event) => {
    const selectedFile = event.target.files[0];
    if (selectedFile) {
      const fileType = selectedFile.type;
      const fileName = selectedFile.name.toLowerCase();
      
      if (fileType === 'application/pdf' || fileName.endsWith('.pdf') || 
          fileType === 'text/plain' || fileName.endsWith('.txt')) {
        setFile(selectedFile);
        setError(null);
        setResult(null);
        setDownloadUrl(null);
      } else {
        setError('Please select a PDF or TXT file');
        setFile(null);
      }
    }
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      const fileType = droppedFile.type;
      const fileName = droppedFile.name.toLowerCase();
      
      if (fileType === 'application/pdf' || fileName.endsWith('.pdf') || 
          fileType === 'text/plain' || fileName.endsWith('.txt')) {
        setFile(droppedFile);
        setError(null);
        setResult(null);
        setDownloadUrl(null);
      } else {
        setError('Please select a PDF or TXT file');
        setFile(null);
      }
    }
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a file first');
      return;
    }

    setUploading(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(`${API_BASE}/analyze`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      setTaskId(response.data.task_id);
      setStatus(response.data.message);
      setAnalyzing(true);
      setUploading(false);
      
      pollStatus(response.data.task_id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed');
      setUploading(false);
    }
  };

  const pollStatus = async (id) => {
    try {
      const response = await axios.get(`${API_BASE}/status/${id}`);
      const data = response.data;
      
      setStatus(data.message);
      
      if (data.status === 'completed') {
        setProgress(100);
        setResult(data.result);
        setDownloadUrl(data.download_url);
        setAnalyzing(false);
      } else if (data.status === 'failed') {
        setError(data.message);
        setAnalyzing(false);
      } else {
        setTimeout(() => pollStatus(id), 2000);
      }
    } catch (err) {
      setError('Failed to get status');
      setAnalyzing(false);
    }
  };

  const handleDownload = async () => {
    if (downloadUrl && taskId) {
      try {
        const response = await axios.get(`${API_BASE}${downloadUrl}`, {
          responseType: 'blob',
        });
        
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', 'legal_analysis.txt');
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
      } catch (err) {
        setError('Download failed');
      }
    }
  };

  const resetAnalysis = () => {
    setFile(null);
    setTaskId(null);
    setStatus('');
    setResult(null);
    setError(null);
    setDownloadUrl(null);
    setAnalyzing(false);
    setUploading(false);
    setProgress(0);
  };

  const formatAnalysisResult = (text) => {
    if (!text) return '';
    
    const sections = text.split(/(?=SHORT SUMMARY:|ISSUE:|RULE:|ANALYSIS:|CONCLUSION:|LEGAL ADVICE:)/);
    
    return sections.map((section, index) => {
      if (!section.trim()) return null;
      
      const lines = section.split('\n');
      const header = lines[0];
      const content = lines.slice(1).join('\n').trim();
      
      if (!header) return null;
      
      const sectionColors = {
        'SHORT SUMMARY:': 'from-purple-600 to-pink-600',
        'ISSUE:': 'from-blue-600 to-cyan-600',
        'RULE:': 'from-green-600 to-emerald-600',
        'ANALYSIS:': 'from-orange-600 to-red-600',
        'CONCLUSION:': 'from-indigo-600 to-purple-600',
        'LEGAL ADVICE:': 'from-pink-600 to-rose-600'
      };
      
      const gradientClass = sectionColors[header] || 'from-gray-600 to-gray-800';
      
      return (
        <div key={index} className="mb-8 relative">
          <div className={`absolute inset-0 bg-gradient-to-r ${gradientClass} rounded-lg opacity-10`}></div>
          <div className="relative bg-white rounded-lg shadow-md border border-gray-100 p-6">
            <h3 className={`text-xl font-bold mb-4 bg-gradient-to-r ${gradientClass} bg-clip-text text-transparent`}>
              {header}
            </h3>
            <div className="text-gray-700 leading-relaxed whitespace-pre-wrap">
              {content}
            </div>
          </div>
        </div>
      );
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* Animated background elements */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-20 w-72 h-72 bg-purple-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse"></div>
        <div className="absolute top-40 right-20 w-72 h-72 bg-cyan-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse animation-delay-2000"></div>
        <div className="absolute bottom-20 left-1/2 w-72 h-72 bg-pink-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse animation-delay-4000"></div>
      </div>

      <div className="relative z-10 container mx-auto px-4 py-8 max-w-6xl">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="flex justify-center items-center mb-6">
            <div className="relative">
              <Scale className="h-16 w-16 text-white mr-4" />
              <Sparkles className="h-8 w-8 text-yellow-400 absolute -top-2 -right-2 animate-pulse" />
            </div>
            <h1 className="text-6xl font-bold text-white mb-0">
              Legal Text Summarizer
            </h1>
            <div className="relative">
              <Brain className="h-16 w-16 text-white ml-4" />
              <Zap className="h-8 w-8 text-cyan-400 absolute -top-2 -left-2 animate-pulse" />
            </div>
          </div>
          <p className="text-xl text-gray-300 max-w-3xl mx-auto leading-relaxed">
            Transform complex legal documents into clear, actionable insights with cutting-edge AI analysis
          </p>
          <div className="flex justify-center items-center mt-6 space-x-8">
            <div className="flex items-center text-gray-300">
              <Globe className="h-5 w-5 mr-2 text-cyan-400" />
              <span>Powered by Gemini AI</span>
            </div>
            <div className="flex items-center text-gray-300">
              <FileCheck className="h-5 w-5 mr-2 text-green-400" />
              <span>IRAC Method Analysis</span>
            </div>
          </div>
        </div>

        {/* Upload Section */}
        {!analyzing && !result && (
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl shadow-2xl border border-white/20 p-8 mb-8">
            <div
              className={`border-2 border-dashed rounded-xl p-12 text-center transition-all duration-300 ${
                isDragging 
                  ? 'border-cyan-400 bg-cyan-500/10 scale-105' 
                  : file 
                  ? 'border-green-400 bg-green-500/10' 
                  : 'border-gray-400/50 bg-white/5 hover:border-cyan-400/50 hover:bg-white/10'
              }`}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
            >
              <div className={`transition-transform duration-300 ${isDragging ? 'scale-110' : 'scale-100'}`}>
                <Upload className="mx-auto h-16 w-16 text-gray-300 mb-6" />
              </div>
              
              <input
                type="file"
                id="file-upload"
                className="hidden"
                accept=".pdf,.txt"
                onChange={handleFileSelect}
              />
              
              <label
                htmlFor="file-upload"
                className="cursor-pointer inline-flex items-center px-8 py-4 bg-gradient-to-r from-cyan-500 to-blue-500 text-white rounded-xl hover:from-cyan-600 hover:to-blue-600 transition-all duration-300 transform hover:scale-105 shadow-lg"
              >
                <FileText className="mr-3 h-6 w-6" />
                Choose Your Document
              </label>
              
              <p className="mt-6 text-gray-300 text-lg">
                or drag and drop your PDF or TXT file here
              </p>
              
              {file && (
                <div className="mt-8 p-4 bg-green-500/20 border border-green-400/50 rounded-xl flex items-center justify-between backdrop-blur-sm">
                  <div className="flex items-center">
                    <FileText className="h-6 w-6 text-green-400 mr-3" />
                    <span className="text-green-300 font-medium">{file.name}</span>
                  </div>
                  <button
                    onClick={() => setFile(null)}
                    className="text-green-400 hover:text-green-300 transition-colors"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
              )}
            </div>

            {error && (
              <div className="mt-6 p-4 bg-red-500/20 border border-red-400/50 rounded-xl flex items-center backdrop-blur-sm">
                <AlertCircle className="h-6 w-6 text-red-400 mr-3" />
                <span className="text-red-300">{error}</span>
              </div>
            )}

            <div className="mt-8 flex justify-center">
              <button
                onClick={handleUpload}
                disabled={!file || uploading}
                className={`px-8 py-4 rounded-xl font-semibold text-lg transition-all duration-300 transform ${
                  !file || uploading
                    ? 'bg-gray-600/50 text-gray-400 cursor-not-allowed'
                    : 'bg-gradient-to-r from-purple-500 to-pink-500 text-white hover:from-purple-600 hover:to-pink-600 shadow-xl hover:scale-105'
                }`}
              >
                {uploading ? (
                  <>
                    <Loader2 className="animate-spin h-6 w-6 mr-3" />
                    Processing...
                  </>
                ) : (
                  <>
                    <Brain className="h-6 w-6 mr-3" />
                    Analyze Document
                    <ArrowRight className="h-6 w-6 ml-3" />
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Analysis Progress */}
        {analyzing && (
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl shadow-2xl border border-white/20 p-8 mb-8">
            <div className="text-center">
              <div className="relative inline-flex items-center justify-center">
                <Loader2 className="animate-spin h-16 w-16 text-cyan-400 mb-6" />
                <Brain className="absolute h-8 w-8 text-purple-400 animate-pulse" />
              </div>
              <h3 className="text-2xl font-bold text-white mb-4">
                AI Analysis in Progress
              </h3>
              <p className="text-gray-300 mb-6 text-lg">{status}</p>
              <div className="w-full bg-gray-700/50 rounded-full h-4 backdrop-blur-sm">
                <div 
                  className="bg-gradient-to-r from-cyan-500 to-purple-500 h-4 rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${progress}%` }}
                ></div>
              </div>
              <p className="text-gray-400 mt-4">{progress}% Complete</p>
            </div>
          </div>
        )}

        {/* Results Section */}
        {result && (
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl shadow-2xl border border-white/20 p-8 mb-8">
            <div className="flex items-center justify-between mb-8">
              <div className="flex items-center">
                <div className="relative">
                  <CheckCircle className="h-8 w-8 text-green-400 mr-3" />
                  <Sparkles className="h-4 w-4 text-yellow-400 absolute -top-1 -right-1 animate-pulse" />
                </div>
                <h2 className="text-3xl font-bold text-white">Analysis Complete</h2>
              </div>
              <div className="flex space-x-4">
                <button
                  onClick={handleDownload}
                  className="inline-flex items-center px-6 py-3 bg-gradient-to-r from-green-500 to-emerald-500 text-white rounded-xl hover:from-green-600 hover:to-emerald-600 transition-all duration-300 transform hover:scale-105 shadow-lg"
                >
                  <Download className="h-5 w-5 mr-2" />
                  Download Report
                </button>
                <button
                  onClick={resetAnalysis}
                  className="inline-flex items-center px-6 py-3 bg-white/20 text-white rounded-xl hover:bg-white/30 transition-all duration-300 transform hover:scale-105 backdrop-blur-sm border border-white/20"
                >
                  Analyze Another
                </button>
              </div>
            </div>
            
            <div className="space-y-6">
              {formatAnalysisResult(result)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
