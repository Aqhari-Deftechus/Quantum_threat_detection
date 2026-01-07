import React, { useState } from 'react';

const SignUp = ({ setCurrentPage }) => {
    const [formData, setFormData] = useState({
        username: '',
        password: '',
        PersonName: '',
        Position: '',
        Department: '',
        Company: '',
        AccessLevel: 'Admin', // Default to Admin
        EMail: '',
        Phone: ''
    });
    const [message, setMessage] = useState('');
    const [isSuccess, setIsSuccess] = useState(false);
    const [isLoading, setIsLoading] = useState(false);

    const ACCESS_LEVELS = ["Admin", "SuperAdmin"];

    const handleChange = (e) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        setMessage('');

        const formBody = new FormData();
        Object.keys(formData).forEach(key => {
            formBody.append(key, formData[key]);
        });

        try {
            const response = await fetch('http://127.0.0.1:8000/signup', {
                method: 'POST',
                body: formBody
            });

            const data = await response.json();

            if (response.ok) {
                setIsSuccess(true);
                setMessage(`✅ Account created! Assigned Badge ID: ${data.badgeID}`);
                setFormData({
                    username: '', password: '', PersonName: '', Position: '',
                    Department: '', Company: '', AccessLevel: 'Admin', EMail: '', Phone: ''
                });
            } else {
                setIsSuccess(false);
                setMessage(`❌ Error: ${data.detail || 'Registration failed'}`);
            }
        } catch (error) {
            setIsSuccess(false);
            setMessage('❌ Network error. Ensure backend is running.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gray-100 p-6">
            <div className="max-w-2xl w-full bg-white rounded-xl shadow-lg p-8">
                <h2 className="text-3xl font-extrabold text-gray-800 text-center mb-6">Register New User</h2>

                {message && (
                    <div className={`p-3 rounded-lg text-sm mb-6 text-center font-medium ${isSuccess ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                        {message}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-6">
                    <div className="bg-blue-50 p-4 rounded-lg border border-blue-100">
                        <h3 className="text-lg font-semibold text-blue-800 mb-3">Account Credentials</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Username</label>
                                <input type="text" name="username" value={formData.username} onChange={handleChange} required className="mt-1 w-full p-2 border border-gray-300 rounded-lg focus:ring-blue-500 outline-none" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Password</label>
                                <input type="password" name="password" value={formData.password} onChange={handleChange} required className="mt-1 w-full p-2 border border-gray-300 rounded-lg focus:ring-blue-500 outline-none" />
                            </div>
                        </div>
                    </div>

                    <div>
                        <h3 className="text-lg font-semibold text-gray-700 mb-3 border-b pb-2">Personnel Information</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="md:col-span-2">
                                <label className="block text-sm font-medium text-gray-700">Full Name</label>
                                <input type="text" name="PersonName" value={formData.PersonName} onChange={handleChange} required className="mt-1 w-full p-2 border border-gray-300 rounded-lg focus:ring-blue-500 outline-none" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Email</label>
                                <input type="email" name="EMail" value={formData.EMail} onChange={handleChange} required className="mt-1 w-full p-2 border border-gray-300 rounded-lg focus:ring-blue-500 outline-none" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Phone</label>
                                <input type="tel" name="Phone" value={formData.Phone} onChange={handleChange} required className="mt-1 w-full p-2 border border-gray-300 rounded-lg focus:ring-blue-500 outline-none" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Company</label>
                                <input type="text" name="Company" value={formData.Company} onChange={handleChange} required className="mt-1 w-full p-2 border border-gray-300 rounded-lg focus:ring-blue-500 outline-none" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Department</label>
                                <input type="text" name="Department" value={formData.Department} onChange={handleChange} required className="mt-1 w-full p-2 border border-gray-300 rounded-lg focus:ring-blue-500 outline-none" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Position</label>
                                <input type="text" name="Position" value={formData.Position} onChange={handleChange} required className="mt-1 w-full p-2 border border-gray-300 rounded-lg focus:ring-blue-500 outline-none" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Access Level</label>
                                <select name="AccessLevel" value={formData.AccessLevel} onChange={handleChange} required className="mt-1 w-full p-2 border border-gray-300 rounded-lg focus:ring-blue-500 outline-none bg-white">
                                    {ACCESS_LEVELS.map(level => (
                                        <option key={level} value={level}>{level}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    </div>

                    <button type="submit" disabled={isLoading} className="w-full bg-blue-600 text-white font-bold py-3 rounded-lg hover:bg-blue-700 transition duration-300 disabled:bg-blue-300">
                        {isLoading ? 'Registering...' : 'Create Account'}
                    </button>
                </form>

                <div className="mt-6 text-center">
                    <p className="text-sm text-gray-600">
                        Already have an account? <button onClick={() => setCurrentPage('Login')} className="text-blue-600 font-semibold hover:underline">Log In</button>
                    </p>
                </div>
            </div>
        </div>
    );
};

export default SignUp;