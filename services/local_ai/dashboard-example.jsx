// Trading Dashboard AI Model Selector Component
// Add this to your trading portal for dynamic model selection

import React, { useState, useEffect } from 'react';

const AIModelSelector = () => {
  const [models, setModels] = useState({});
  const [selectedModel, setSelectedModel] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Load available models on component mount
    fetchAvailableModels();
  }, []);

  const fetchAvailableModels = async () => {
    try {
      const response = await fetch('http://localhost:3008/dashboard/models');
      const data = await response.json();
      setModels(data);
    } catch (error) {
      console.error('Failed to fetch models:', error);
    }
  };

  const selectModelForTask = async (taskType, preferSpeed = true) => {
    setLoading(true);
    try {
      const response = await fetch(`http://localhost:3008/dashboard/select-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_type: taskType, prefer_speed: preferSpeed })
      });
      const result = await response.json();
      setSelectedModel(result);
    } catch (error) {
      console.error('Failed to select model:', error);
    }
    setLoading(false);
  };

  const sendSmartQuery = async (message, taskType = 'general') => {
    try {
      const response = await fetch('http://localhost:3008/v1/chat/completions/smart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'auto-select', // Will be auto-selected
          messages: [{ role: 'user', content: message }],
          task_type: taskType,
          prefer_speed: true
        })
      });
      const result = await response.json();
      return result;
    } catch (error) {
      console.error('Smart query failed:', error);
    }
  };

  return (
    <div className="ai-model-selector p-6 bg-white rounded-lg shadow-lg">
      <h3 className="text-xl font-bold mb-4">🤖 AI Trading Assistant</h3>
      
      {/* Quick Task Buttons */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
        <button 
          onClick={() => selectModelForTask('real_time_trading', true)}
          className="p-3 bg-green-100 hover:bg-green-200 rounded text-sm font-medium"
        >
          ⚡ Real-Time Trading
        </button>
        <button 
          onClick={() => selectModelForTask('financial_analysis', false)}
          className="p-3 bg-blue-100 hover:bg-blue-200 rounded text-sm font-medium"
        >
          📊 Financial Analysis  
        </button>
        <button 
          onClick={() => selectModelForTask('code_generation', true)}
          className="p-3 bg-purple-100 hover:bg-purple-200 rounded text-sm font-medium"
        >
          💻 Code Generation
        </button>
        <button 
          onClick={() => selectModelForTask('market_sentiment', true)}
          className="p-3 bg-yellow-100 hover:bg-yellow-200 rounded text-sm font-medium"
        >
          📈 Market Sentiment
        </button>
        <button 
          onClick={() => selectModelForTask('research', false)}
          className="p-3 bg-indigo-100 hover:bg-indigo-200 rounded text-sm font-medium"
        >
          🧠 Deep Research
        </button>
        <button 
          onClick={() => selectModelForTask('document_search', true)}
          className="p-3 bg-gray-100 hover:bg-gray-200 rounded text-sm font-medium"
        >
          🔍 Document Search
        </button>
      </div>

      {/* Selected Model Info */}
      {selectedModel && (
        <div className="bg-gray-50 p-4 rounded mb-4">
          <h4 className="font-semibold">🎯 Selected Model:</h4>
          <p className="text-sm text-gray-600">
            <strong>{selectedModel.model_name}</strong> - {selectedModel.best_for}
          </p>
          <div className="flex gap-2 mt-2">
            <span className={`px-2 py-1 rounded text-xs ${
              selectedModel.speed === 'ultra-fast' ? 'bg-green-100 text-green-800' :
              selectedModel.speed === 'fast' ? 'bg-blue-100 text-blue-800' :
              'bg-gray-100 text-gray-800'
            }`}>
              {selectedModel.speed}
            </span>
            <span className={`px-2 py-1 rounded text-xs ${
              selectedModel.quality === 'premium' ? 'bg-purple-100 text-purple-800' :
              selectedModel.quality === 'excellent' ? 'bg-blue-100 text-blue-800' :
              'bg-gray-100 text-gray-800'
            }`}>
              {selectedModel.quality}
            </span>
          </div>
        </div>
      )}

      {/* Available Models by Speed */}
      {models.models_by_speed && (
        <div className="mt-6">
          <h4 className="font-semibold mb-3">📊 Available Models by Speed:</h4>
          
          {Object.entries(models.models_by_speed).map(([speed, modelList]) => (
            <div key={speed} className="mb-3">
              <h5 className="text-sm font-medium capitalize mb-1">
                {speed === 'ultra-fast' && '⚡'} 
                {speed === 'fast' && '🚀'} 
                {speed === 'balanced' && '🎯'} 
                {speed === 'slow' && '🧠'} 
                {speed}
              </h5>
              <div className="flex flex-wrap gap-2">
                {modelList.map((model) => (
                  <div 
                    key={model.id}
                    className={`px-3 py-1 rounded text-xs border ${
                      model.loaded ? 'bg-green-50 border-green-200' : 'bg-gray-50 border-gray-200'
                    }`}
                  >
                    {model.name} ({model.size})
                    {model.loaded && <span className="ml-1 text-green-600">✓</span>}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Recommendations */}
      {models.recommendations && (
        <div className="mt-6 p-4 bg-blue-50 rounded">
          <h4 className="font-semibold mb-2">💡 Quick Recommendations:</h4>
          <div className="text-sm space-y-1">
            <p><strong>Real-time trading:</strong> Ultra-fast responses</p>
            <p><strong>Financial analysis:</strong> Balanced speed + quality</p>
            <p><strong>Deep research:</strong> Highest quality models</p>
            <p><strong>Code generation:</strong> Specialized code models</p>
          </div>
        </div>
      )}

      {loading && (
        <div className="text-center py-4">
          <div className="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          <p className="text-sm text-gray-600 mt-2">Loading model...</p>
        </div>
      )}
    </div>
  );
};

export default AIModelSelector;