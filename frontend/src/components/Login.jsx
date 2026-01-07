import React, { useState } from 'react';

const Login = ({ setCurrentPage, onLoginSuccess }) => {
    const [credentials, setCredentials] = useState({ username: '', password: '' });
    const [message, setMessage] = useState('');
    const [loading, setLoading] = useState(false);

    const handleChange = (e) => {
        setCredentials({ ...credentials, [e.target.name]: e.target.value });
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setMessage('');

        const formData = new FormData();
        formData.append('username', credentials.username);
        formData.append('password', credentials.password);

        try {
            const response = await fetch('http://127.0.0.1:8000/login', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (response.ok) {
                // 1. Store the token securely in localStorage
                localStorage.setItem('authToken', data.access_token);
                localStorage.setItem('badgeID', data.badgeID);
                localStorage.setItem('username', data.username);
                localStorage.setItem('role', data.role);

                // 2. Notify parent component (App.jsx) that login was successful
                if (onLoginSuccess) {
                    onLoginSuccess({
                        badgeID: data.badgeID,
                        username: data.username,
                        role: data.role
                    });
                }
            } else {
                setMessage(`❌ Login Failed: ${data.detail || 'Invalid credentials'}`);
            }
        } catch (error) {
            setMessage('❌ Network error. Ensure backend is running.');
            console.error("Login error:", error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gray-100 p-6">
            <div className="max-w-md w-full bg-white rounded-xl shadow-lg p-8">
                <div className="text-center mb-8">
                    <h2 className="text-3xl font-extrabold text-gray-800">Admin Portal</h2>
                    <p className="text-gray-500 mt-2">Please sign in to your account</p>
                </div>

                {message && (
                    <div className="bg-red-100 text-red-700 p-3 rounded-lg text-sm mb-6 text-center font-medium">
                        {message}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-6">
                    <div>
                        <label className="block text-sm font-medium text-gray-700">Username</label>
                        <input
                            type="text"
                            name="username"
                            value={credentials.username}
                            onChange={handleChange}
                            required
                            className="mt-1 w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition"
                            placeholder="Enter your username"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700">Password</label>
                        <input
                            type="password"
                            name="password"
                            value={credentials.password}
                            onChange={handleChange}
                            required
                            className="mt-1 w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition"
                            placeholder="Enter your password"
                        />
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-blue-600 text-white font-bold py-3 rounded-lg hover:bg-blue-700 transition duration-300 shadow-md disabled:bg-blue-300"
                    >
                        {loading ? 'Signing In...' : 'Sign In'}
                    </button>
                </form>

                <div className="mt-8 text-center">
                    <p className="text-sm text-gray-600">
                        Don't have an account?{' '}
                        <button
                            onClick={() => setCurrentPage('SignUp')}
                            className="text-blue-600 font-semibold hover:underline focus:outline-none"
                        >
                            Register here
                        </button>
                    </p>
                </div>
            </div>
        </div>
    );
};

export default Login;