import React, { useState,useEffect } from 'react';
import { User, Shield, FileText, LogIn, UserPlus, Search, Edit, Trash2, Upload, CheckCircle, XCircle, Menu, X } from 'lucide-react';
import EmployeeRegistrationForm from './components/EmployeeRegistrationForm.jsx';
import IdentityManagement from './components/IdentityManagement.jsx';
import Login from './components/Login.jsx';
import SignUp from './components/SignUp.jsx';


const HomePage = ({ setCurrentPage }) => {
    // Define the core modules for the system
    const modules = [
        {
            title: "Employee Registration",
            description: "Register new personnel, assign badge IDs, and upload face recognition data.",
            icon: "👤",
            page: 'Register'
        },
        {
            title: "Identity Management",
            description: "View, update, or deactivate existing employee records and certificates.",
            icon: "📜",
            page: 'Update' // <-- TARGET PAGE FOR NEW MODULE
        },
        {
            title: "Access Logs",
            description: "Review entry/exit logs and system activity within restricted zones.",
            icon: "🚪",
            page: 'Logs'
        },
        {
            title: "Face Data Upload",
            description: "Bulk upload or retrain face data for existing personnel.",
            icon: "👁️",
            page: 'Face'
        },
    ];

    return (
        <div className="p-8">
            <header className="mb-10 text-center">
                <h1 className="text-4xl font-extrabold text-gray-800">Admin Dashboard</h1>
                <p className="text-xl text-gray-500 mt-2">Restricted Area Identity & Access Control</p>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 gap-6">
                {modules.map((module) => (
                    <div
                        key={module.page}
                        onClick={() => setCurrentPage(module.page)}
                        className={`bg-white p-6 rounded-xl shadow-lg border-t-4 transition duration-300 transform hover:scale-[1.02] cursor-pointer
                            ${module.page === 'Register' ? 'border-blue-600 hover:shadow-xl' : (module.page === 'Update' ? 'border-indigo-600 hover:shadow-xl' : 'border-gray-300 hover:shadow-md')}`}
                    >
                        <div className="flex items-center space-x-4">
                            <span className="text-4xl">{module.icon}</span>
                            <div>
                                <h2 className="text-xl font-semibold text-gray-700">{module.title}</h2>
                                <p className="text-gray-500 text-sm mt-1">{module.description}</p>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            <div className="mt-12 text-center text-sm text-gray-400">
                <p>System Status: <span className="text-green-500 font-medium">Online</span> | Last PKL Update: Just now</p>
            </div>
        </div>
    );
};

// --- MAIN APP ---
const App = () => {
    const [isLoading, setIsLoading] = useState(true);
    const [currentPage, setCurrentPage] = useState('Login');
    const [currentUser, setCurrentUser] = useState(null);

    // --- ADDED: SESSION RESTORATION EFFECT ---
    useEffect(() => {
        const token = localStorage.getItem('authToken');
        const badgeID = localStorage.getItem('badgeID');
        const username = localStorage.getItem('username');

        if (token) {
            setCurrentUser({ badgeID, username });
            const lastPage = localStorage.getItem('lastPage');
            setCurrentPage(lastPage || 'Home');
        }
        setIsLoading(false);
    }, []);

    useEffect(() => {
        // Only save the page if the user is logged in and it's a valid dashboard page
        if (currentUser && currentPage !== 'Login' && currentPage !== 'SignUp') {
            localStorage.setItem('lastPage', currentPage);
        }
    }, [currentPage, currentUser]);

    const handleLoginSuccess = (userData) => {
        setCurrentUser(userData);
        setCurrentPage('Home');
    };

    const handleLogout = () => {
        setCurrentUser(null);
        setCurrentPage('Login');
        localStorage.removeItem('authToken');
        localStorage.removeItem('badgeID');
        localStorage.removeItem('username');
        localStorage.removeItem('lastPage');
    };

    const renderPage = () => {
        switch (currentPage) {
            case 'Login': return <Login setCurrentPage={setCurrentPage} onLoginSuccess={handleLoginSuccess} />;
            case 'SignUp': return <SignUp setCurrentPage={setCurrentPage} />;
            case 'Home': return <HomePage setCurrentPage={setCurrentPage} />;
            case 'Register': return <EmployeeRegistrationForm setCurrentPage={setCurrentPage} />;
            case 'Update': return <IdentityManagement setCurrentPage={setCurrentPage} />;
            default: return <Login setCurrentPage={setCurrentPage} onLoginSuccess={handleLoginSuccess} />;
        }
    };

    if (isLoading) {
        return <div className="min-h-screen flex items-center justify-center bg-gray-100"><div className="text-gray-500 font-semibold animate-pulse">Loading secure session...</div></div>;
    }

    if (currentPage === 'Login' || currentPage === 'SignUp') {
        return <div className="min-h-screen bg-gray-100 text-gray-800 font-sans">{renderPage()}</div>;
    }

    return (
        <div className="min-h-screen bg-gray-100 text-gray-800 font-sans">
            <nav className="bg-white border-b border-gray-200 sticky top-0 z-30">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex justify-between items-center h-16">
                        <div className="flex items-center gap-2 cursor-pointer" onClick={() => setCurrentPage('Home')}>
                            <Shield className="w-6 h-6 text-indigo-600" />
                            <span className="text-xl font-bold text-gray-800">Employee Management (EMMA)</span>
                        </div>
                        <div className="flex items-center space-x-4">
                            <div className="hidden md:flex flex-col text-right">
                                <span className="text-sm font-bold text-gray-700">{currentUser?.username || 'Admin'}</span>
                                <span className="text-xs text-gray-500">{currentUser?.badgeID || 'ID'}</span>
                            </div>
                            <button onClick={handleLogout} className="bg-gray-100 hover:bg-red-50 hover:text-red-600 text-gray-600 px-4 py-2 rounded-lg text-sm font-medium transition">Logout</button>
                        </div>
                    </div>
                </div>
            </nav>
            <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
                {renderPage()}
            </main>
        </div>
    );
}

export default App;