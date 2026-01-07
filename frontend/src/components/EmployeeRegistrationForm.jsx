import React, { useState } from 'react';

// --- DATA DEFINITIONS ---
const YEAR_VALUES = ["2035", "2034", "2033", "2032", "2031", "2030", "2029", "2028", "2027", "2026", "2025", "2024", "2023", "2022", "2021", "2020"].sort().reverse();
const MONTH_VALUES = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];
const DAY_VALUES = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31"];
const DEFAULT_DATE = { year: "2035", month: "12", day: "31" };
const API_ENDPOINT = "http://127.0.0.1:8000/employee/register";

const SelectInput = ({ name, options, defaultValue }) => (
    <select name={name} defaultValue={defaultValue || ''} required className="p-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500">
        {options.map(option => (<option key={option} value={option}>{option}</option>))}
    </select>
);

const EmployeeRegistrationForm = ({ setCurrentPage }) => {
    const [message, setMessage] = useState('');
    const [files, setFiles] = useState(null);
    const [formInputs, setFormInputs] = useState({ position: '', department: '', email: '', phone: '' });

    const handleInputChange = (e) => {
        const { name, value } = e.target;
        setFormInputs(prev => ({ ...prev, [name]: value }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setMessage('Registering employee... Please wait.');
        const formData = new FormData(e.target);
        if (files) { for (let i = 0; i < files.length; i++) { formData.append('files', files[i]); } }
        if (formData.getAll('files').length === 0) { setMessage('Error: At least one face image file is required.'); return; }

        const token = localStorage.getItem('authToken');
        if (!token) { setMessage('❌ Error: You are not logged in. Please log in again.'); return; }

        try {
            const response = await fetch(API_ENDPOINT, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData,
            });
            const data = await response.json();
            if (response.ok) {
                setMessage(`✅ Success! BadgeID ${data.badgeID} registered.`);
                e.target.reset();
                setFiles(null);
                setFormInputs({ position: '', department: '', email: '', phone: '' });
            } else {
                setMessage(`❌ Registration Failed (Status ${response.status}): ${data.detail || response.statusText}`);
            }
        } catch (error) {
            setMessage(`❌ Network Error: ${error.message}`);
        }
    };

    return (
        <div className="max-w-3xl mx-auto p-6 bg-white rounded-xl shadow-2xl mt-10">
            <button onClick={() => setCurrentPage('Home')} className="text-blue-600 hover:text-blue-800 flex items-center mb-4 transition duration-150">&larr; Back to Dashboard</button>
            <h2 className="text-3xl font-bold text-gray-800 border-b pb-3 mb-6">Employee Registration</h2>
            <div className={`p-3 rounded-lg mb-4 ${message ? (message.startsWith('✅') ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700') : 'hidden'}`}>{message}</div>
            <form onSubmit={handleSubmit} className="space-y-6">
                <h3 className="text-xl font-semibold text-blue-600 border-l-4 border-blue-600 pl-3">Personnel Details</h3>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div className="flex flex-col"><label className="text-sm font-medium text-gray-700 mb-1">Full Name:</label><input type="text" name="person_name" required className="p-2 border rounded-lg" /></div>
                    <div className="flex flex-col"><label className="text-sm font-medium text-gray-700 mb-1">Badge ID (Unique):</label><input type="text" name="badgeID" required className="p-2 border rounded-lg" /></div>
                    <div className="flex flex-col"><label className="text-sm font-medium text-gray-700 mb-1">Position:</label><input type="text" name="position" value={formInputs.position} onChange={handleInputChange} required className="p-2 border rounded-lg" /></div>
                    <div className="flex flex-col"><label className="text-sm font-medium text-gray-700 mb-1">Department:</label><input type="text" name="department" value={formInputs.department} onChange={handleInputChange} required className="p-2 border rounded-lg" /></div>
                    <div className="flex flex-col"><label className="text-sm font-medium text-gray-700 mb-1">Company:</label><input type="text" name="company" required className="p-2 border rounded-lg" /></div>
                    <div className="flex flex-col"><label className="text-sm font-medium text-gray-700 mb-1">Email:</label><input type="email" name="email" value={formInputs.email} onChange={handleInputChange} required className="p-2 border rounded-lg" /></div>
                    <div className="flex flex-col"><label className="text-sm font-medium text-gray-700 mb-1">Phone:</label><input type="tel" name="phone" value={formInputs.phone} onChange={handleInputChange} required className="p-2 border rounded-lg" /></div>
                </div>
                <h3 className="text-xl font-semibold text-blue-600 border-l-4 border-blue-600 pl-3 pt-6">Certificates & Compliance</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-4 border rounded-lg bg-gray-50">
                    <div className="space-y-4">
                        <label className="text-sm font-medium text-gray-700">Certificate 1 Expiry Date:</label>
                        <div className="flex space-x-2"><SelectInput name="certificate1_year" options={YEAR_VALUES} defaultValue={DEFAULT_DATE.year} /><SelectInput name="certificate1_month" options={MONTH_VALUES} defaultValue={DEFAULT_DATE.month} /><SelectInput name="certificate1_day" options={DAY_VALUES} defaultValue={DEFAULT_DATE.day} /></div>
                        <label className="text-sm font-medium text-gray-700">Certificate 2 Status:</label><SelectInput name="certificate2" options={["0", "1"]} defaultValue="0" />
                    </div>
                    <div className="space-y-4">
                        <label className="text-sm font-medium text-gray-700">Certificate 3 Expiry Date:</label>
                        <div className="flex space-x-2"><SelectInput name="certificate3_year" options={YEAR_VALUES} defaultValue={DEFAULT_DATE.year} /><SelectInput name="certificate3_month" options={MONTH_VALUES} defaultValue={DEFAULT_DATE.month} /><SelectInput name="certificate3_day" options={DAY_VALUES} defaultValue={DEFAULT_DATE.day} /></div>
                        <label className="text-sm font-medium text-gray-700">Certificate 4 Status:</label><SelectInput name="certificate4" options={["0", "1"]} defaultValue="0" />
                    </div>
                </div>
                <h3 className="text-xl font-semibold text-blue-600 border-l-4 border-blue-600 pl-3 pt-6">Face Data</h3>
                <div className="flex flex-col">
                    <label className="text-sm font-medium text-gray-700 mb-1">Upload Images:</label>
                    <input type="file" name="files" accept="image/*" multiple required onChange={(e) => setFiles(e.target.files)} className="file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-violet-50 file:text-violet-700 hover:file:bg-violet-100 p-2 border rounded-lg bg-gray-50" />
                </div>
                <button type="submit" className="w-full py-3 bg-green-600 text-white font-bold rounded-lg shadow-md hover:bg-green-700 transition duration-300">Submit Registration</button>
            </form>
        </div>
    );
};

export default EmployeeRegistrationForm;