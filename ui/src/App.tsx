import React, { useState, useEffect } from 'react';
import DatePicker from 'react-datepicker';
import ReactMarkdown from 'react-markdown';
import "react-datepicker/dist/react-datepicker.css";
import tavilyLogo from '../assets/tavily_logo.svg';
import { FaCalendarAlt, FaClock, FaCogs } from 'react-icons/fa';

type StatusUpdate = {
  type: string;
  content: string;
};

enum MessageTypes {
  CALENDAR_STATUS = "calendar_status",
  CALENDAR_PARSER_STATUS = "calendar_parser_status",
  REACT_STATUS = "react_status",
  MARKDOWN_FORMATTER_STATUS = "markdown_formatter_status",
  COMPANY_EVENT = "company_event",
  STREAMING = "streaming"
}

function App() {
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [statusType, setStatusType] = useState<string>('');
  const [companyEvents, setCompanyEvents] = useState<string[]>([]);
  const [streamContent, setStreamContent] = useState<string>('');

  // Clear status when streaming starts, but keep company events visible
  useEffect(() => {
    if (streamContent.length > 0) {
      // Only clear non-company event statuses
      if (statusType !== MessageTypes.COMPANY_EVENT) {
        setStatusType('');
      }
      setLoading(false);
    }
  }, [streamContent, statusType]);

  // Reset states when selecting a new date
  const handleDateSelect = async (date: Date | null) => {
    if (!date) return;
    
    setSelectedDate(date);
    setLoading(true);
    setError('');
    setStreamContent('');
    setStatusType('');
    setCompanyEvents([]);
    
    try {
      const formattedDate = date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });

      const response = await fetch('/api/analyze-meetings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ date: formattedDate }),
      });

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader available');

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const decodedChunk = decoder.decode(value, { stream: true });
        buffer += decodedChunk;

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          
          try {
            const event: StatusUpdate = JSON.parse(line);
            
            switch (event.type) {
              case MessageTypes.CALENDAR_STATUS:
              case MessageTypes.CALENDAR_PARSER_STATUS:
              case MessageTypes.REACT_STATUS:
                setStatusType(event.type);
                break;
              case MessageTypes.COMPANY_EVENT:
                console.log("Company Event received from backend:", event);
                console.log("Content:", event.content);
                
                // Add to the array of company events instead of replacing
                setCompanyEvents(prev => [...prev, event.content]);
                break;
              case MessageTypes.STREAMING:
                setStreamContent(prev => prev + event.content);
                break;
              default:
                console.log('Unknown event type:', event.type);
            }
          } catch (e) {
            console.error('Error parsing event:', e);
          }
        }
      }

    } catch (error) {
      console.error('Error fetching meeting analysis:', error);
      setError('Error analyzing meetings. Please try again.');
      setLoading(false);
    }
  };

  const renderStatusIcon = () => {
    switch (statusType) {
      case MessageTypes.CALENDAR_STATUS:
        return <FaCalendarAlt className="text-blue-500" />;
      case MessageTypes.CALENDAR_PARSER_STATUS:
        return <FaCogs className="text-blue-500" />;
      case MessageTypes.REACT_STATUS:
        return <img src={tavilyLogo} alt="Tavily Logo" className="h-4 w-auto" />;
      case MessageTypes.COMPANY_EVENT:
        return <FaClock className="text-yellow-600" />;
      default:
        return null;
    }
  };

  const getStatusLabel = () => {
    switch (statusType) {
      case MessageTypes.CALENDAR_STATUS:
        return "Accessing calendar";
      case MessageTypes.CALENDAR_PARSER_STATUS:
        return "Processing data";
      case MessageTypes.REACT_STATUS:
        return "Researching";
      default:
        return "";
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      {/* Header with Tavily logo */}
      <header className="w-full bg-white shadow-sm py-4">
        <div className="max-w-7xl mx-auto px-4 flex justify-center items-center">
          <div className="flex items-center gap-2">
            <span className="text-gray-600 text-sm">Powered by</span>
            <img src={tavilyLogo} alt="Tavily Logo" className="h-5" />
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 py-8">
        <div className="max-w-3xl mx-auto px-4">
          <div className="bg-white shadow-lg rounded-2xl p-8">
            <div className="max-w-2xl mx-auto">
              <h1 className="text-xl font-medium mb-8 text-center text-gray-600">Your Meetings, Fully Prepared</h1>
              
              <div className="mb-8 flex flex-col items-center">
                <DatePicker
                  selected={selectedDate}
                  onChange={handleDateSelect}
                  className="mt-1 w-64 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm p-2 border text-center cursor-pointer"
                  dateFormat="MMMM d, yyyy"
                  placeholderText="Select a date to prep for"
                />
              </div>

              {/* Company events section - display all events */}
              {companyEvents.length > 0 && (
                <div className="text-center mb-4 space-y-2">
                  {companyEvents.map((event, index) => (
                    <div key={index} className="flex items-center justify-center gap-2 bg-yellow-50 p-3 rounded-lg shadow-sm border border-yellow-200">
                      <div className="text-xl"><FaClock className="text-yellow-600" /></div>
                      <div className="text-sm font-medium text-gray-700">{event}</div>
                    </div>
                  ))}
                </div>
              )}

              {/* Loading and status indicators (except company events) */}
              {(loading || (statusType && statusType !== MessageTypes.COMPANY_EVENT)) && (
                <div className="text-center py-4">
                  {loading && (
                    <div className="flex items-center justify-center space-x-2 mb-4">
                      <div 
                        className="h-3 w-3 rounded-full bg-[#8FBCFA] animate-bounce"
                        style={{ 
                          animationDuration: "0.8s"
                        }}
                      ></div>
                      <div 
                        className="h-3 w-3 rounded-full bg-[#FF9A9D] animate-bounce"
                        style={{ 
                          animationDelay: "0.15s",
                          animationDuration: "0.8s"
                        }}
                      ></div>
                      <div 
                        className="h-3 w-3 rounded-full bg-[#F6D785] animate-bounce"
                        style={{ 
                          animationDelay: "0.3s",
                          animationDuration: "0.8s"
                        }}
                      ></div>
                    </div>
                  )}
                  {statusType && statusType !== MessageTypes.COMPANY_EVENT && (
                    <div className="flex items-center justify-center gap-2 bg-gray-50 p-3 rounded-lg shadow-sm">
                      <div className="text-xl">{renderStatusIcon()}</div>
                      <div className="text-sm font-medium text-gray-700">{getStatusLabel()}</div>
                    </div>
                  )}
                </div>
              )}

              {error && (
                <div className="text-red-600 bg-red-50 p-4 rounded-lg">
                  {error}
                </div>
              )}

              {streamContent && (
                <div className="mt-8 prose prose-slate max-w-none">
                  <div className="bg-white text-gray-800">
                    <ReactMarkdown
                      components={{
                        h2: ({node, ...props}) => <h2 className="text-xl font-bold mt-6 mb-4 text-gray-900" {...props} />,
                        h3: ({node, ...props}) => <h3 className="text-lg font-semibold mt-4 mb-2 text-gray-800" {...props} />,
                        h4: ({node, ...props}) => <h4 className="text-base font-semibold mt-3 mb-1 text-gray-700" {...props} />,
                        p: ({node, ...props}) => <p className="my-2 text-gray-600" {...props} />,
                        ul: ({node, ...props}) => <ul className="list-disc ml-6 my-2" {...props} />,
                        li: ({node, ...props}) => <li className="text-gray-600 my-1" {...props} />
                      }}
                    >
                      {streamContent}
                    </ReactMarkdown>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App; 