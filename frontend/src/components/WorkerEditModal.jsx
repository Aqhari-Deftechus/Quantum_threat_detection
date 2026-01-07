import React, { useState, useEffect } from 'react';

// API Endpoints
const API_WORKER_DETAIL = (id) => `http://127.0.0.1:8000/worker/${id}`;
const API_UPDATE_IDENTITY = `http://127.0.0.1:8000/workeridentity/update`;
const API_UPDATE_CERTIFICATE = `http://127.0.0.1:8000/identitymanagement/update`;

// --- ENUM Definitions ---
const ACCESS_LEVEL_VALUES = ["Visitor", "Employee", "Contractor", "Security", "Admin", "SuperAdmin"];
const STATUS_VALUES = ["Active", "Suspended", "Terminated"];
const CERTBOOL_VALUES = ["0", "1"];

const YEAR_VALUES = [
    "2035", "2034", "2033", "2032", "2031", "2030", "2029", "2028", "2027", "2026", "2025",
    "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017", "2016", "2015"
].sort().reverse();
const MONTH_VALUES = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];
const DAY_VALUES = [
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15",
    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31"
];

// Helper to format date string (YYYY-MM-DD) into date parts for selects
const dateToParts = (dateString) => {
    if (!dateString || dateString.toLowerCase() === 'n/a' || dateString.startsWith('2035')) {
        return { year: '2035', month: '12', day: '31' };
    }
    const [year, month, day] = dateString.split('-');
    if (year && month && day) return { year, month, day };
    return { year: '2035', month: '12', day: '31' };
};

// Reusable Select Input Component
const SelectInput = ({ name, options, defaultValue, onChange, disabled = false }) => (
    <select
        name={name}
        defaultValue={defaultValue || ''}
        onChange={onChange}
        required
        disabled={disabled}
        className="p-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 w-full"
    >
        {options.map(option => (
            <option key={option} value={option}>{option}</option>
        ))}
    </select>
);

// --- Component Helpers ---
const ModalOverlay = ({ children }) => (
    <div className="fixed inset-0 bg-gray-900 bg-opacity-75 flex items-center justify-center z-50 p-4">
        <div className="bg-white p-8 rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            {children}
        </div>
    </div>
);

const InputGroup = ({ label, name, value, onChange, type = 'text', readOnly = false }) => (
    <div className="flex flex-col">
        <label className="text-sm font-medium text-gray-700 mb-1">{label}:</label>
        <input
            type={type}
            name={name}
            value={value || ''}
            onChange={onChange}
            required
            readOnly={readOnly}
            className={`p-2 border rounded-lg ${readOnly ? 'bg-gray-100 text-gray-500' : 'bg-white'}`}
        />
    </div>
);

// --- Main Component ---
const WorkerEditModal = ({ badgeID, closeModal, onUpdateSuccess }) => {
    const [workerData, setWorkerData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [message, setMessage] = useState('');

    const [cert1Date, setCert1Date] = useState({ year: '2035', month: '12', day: '31' });
    const [cert3Date, setCert3Date] = useState({ year: '2035', month: '12', day: '31' });

    // --- Initial Data Fetch ---
    useEffect(() => {
        const fetchWorkerDetails = async () => {
            try {
                const token = localStorage.getItem('authToken');
                if (!token) throw new Error("No session token found. Please login.");

                const response = await fetch(API_WORKER_DETAIL(badgeID), {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (response.status === 401) throw new Error("Session expired. Please login again.");
                if (!response.ok) throw new Error("Failed to fetch worker details.");

                const data = await response.json();
                setWorkerData(data);

                setCert1Date(dateToParts(data.Certificate1));
                setCert3Date(dateToParts(data.Certificate3));

            } catch (err) {
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        fetchWorkerDetails();
    }, [badgeID]);

    // --- Change Handlers ---
    const handleIdentityChange = (e) => {
        const { name, value } = e.target;
        setWorkerData(prev => ({ ...prev, [name]: value }));
    };

    const handleCertDateChange = (certNum, e) => {
        const { name, value } = e.target;
        const part = name.split('_')[1];
        if (certNum === 1) setCert1Date(prev => ({ ...prev, [part]: value }));
        else if (certNum === 3) setCert3Date(prev => ({ ...prev, [part]: value }));
    };

    // --- Submission Logic ---
    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        setMessage('Submitting updates...');
        setError(null);

        const token = localStorage.getItem('authToken');
        if (!token) {
            setError("No session token found. Please login.");
            setIsSubmitting(false);
            return;
        }

        try {
            // Identity FormData
            const identityFormData = new FormData();
            identityFormData.append('person_name', workerData?.PersonName || '');
            identityFormData.append('badgeID', workerData?.BadgeID || '');
            identityFormData.append('position', workerData?.Position || '');
            identityFormData.append('department', workerData?.Department || '');
            identityFormData.append('company', workerData?.Company || '');
            identityFormData.append('access_level', workerData?.AccessLevel || '');
            identityFormData.append('email', workerData?.EMail || '');
            identityFormData.append('phone', workerData?.Phone || '');
            identityFormData.append('status', workerData?.Status || '');

            // Update Identity
            const identityResponse = await fetch(API_UPDATE_IDENTITY, {
                method: 'PUT',
                headers: { 'Authorization': `Bearer ${token}` },
                body: identityFormData,
            });

            if (!identityResponse.ok) throw new Error("Identity update failed.");

            // Update Certificates only if not Admin/SuperAdmin
            if (!["Admin", "SuperAdmin"].includes(workerData?.AccessLevel)) {
                const certFormData = new FormData();
                certFormData.append('badgeID', workerData?.BadgeID || '');
                certFormData.append('certificate1_year', cert1Date.year);
                certFormData.append('certificate1_month', cert1Date.month);
                certFormData.append('certificate1_day', cert1Date.day);
                certFormData.append('certificate2', workerData?.Certificate2 || '0');
                certFormData.append('certificate3_year', cert3Date.year);
                certFormData.append('certificate3_month', cert3Date.month);
                certFormData.append('certificate3_day', cert3Date.day);
                certFormData.append('certificate4', workerData?.Certificate4 || '0');

                const certResponse = await fetch(API_UPDATE_CERTIFICATE, {
                    method: 'PUT',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: certFormData,
                });

                if (!certResponse.ok) throw new Error("Certificate update failed.");
            }

            setMessage(`✅ Success! Worker ${workerData?.PersonName} updated.`);
            setTimeout(() => { onUpdateSuccess(); }, 1000);

        } catch (err) {
            setError(err.message);
            setMessage(`❌ Update Failed: ${err.message}`);
        } finally {
            setIsSubmitting(false);
        }
    };

    if (loading || !workerData) return <ModalOverlay><div className="text-center p-10">Loading...</div></ModalOverlay>;

    const disableCertificates = ["Admin", "SuperAdmin"].includes(workerData?.AccessLevel);

    return (
        <ModalOverlay>
            <h2 className="text-2xl font-bold text-indigo-600 border-b pb-3 mb-6 flex justify-between items-center">
                Edit Worker: {workerData?.PersonName || '...'} ({workerData?.BadgeID || '...'})
                <button onClick={closeModal} className="text-gray-400 hover:text-gray-700 text-3xl font-light leading-none">&times;</button>
            </h2>

            <div className={`p-3 rounded-lg mb-4 ${message ? (message.startsWith('✅') ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700') : 'hidden'}`}>{message || error}</div>

            <form onSubmit={handleSubmit} className="space-y-6">
                {/* Identity Section */}
                <h3 className="text-xl font-semibold text-gray-700 border-l-4 border-gray-400 pl-3">Identity Details</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <InputGroup label="Full Name" name="PersonName" value={workerData?.PersonName || ''} onChange={handleIdentityChange} readOnly={isSubmitting} />
                    <InputGroup label="Badge ID" name="BadgeID" value={workerData?.BadgeID || ''} readOnly />
                    <InputGroup label="Position" name="Position" value={workerData?.Position || ''} onChange={handleIdentityChange} readOnly={isSubmitting} />
                    <InputGroup label="Department" name="Department" value={workerData?.Department || ''} onChange={handleIdentityChange} readOnly={isSubmitting} />
                    <InputGroup label="Company" name="Company" value={workerData?.Company || ''} onChange={handleIdentityChange} readOnly={isSubmitting} />
                    <InputGroup label="Email" name="EMail" value={workerData?.EMail || ''} type="email" onChange={handleIdentityChange} readOnly={isSubmitting} />
                    <InputGroup label="Phone" name="Phone" value={workerData?.Phone || ''} type="tel" onChange={handleIdentityChange} readOnly={isSubmitting} />

                    <div className="flex flex-col">
                        <label className="text-sm font-medium text-gray-700 mb-1">Access Level:</label>
                        <SelectInput name="AccessLevel" options={ACCESS_LEVEL_VALUES} defaultValue={workerData?.AccessLevel} onChange={handleIdentityChange} disabled={isSubmitting} />
                    </div>

                    <div className="flex flex-col">
                        <label className="text-sm font-medium text-gray-700 mb-1">Status:</label>
                        <SelectInput name="Status" options={STATUS_VALUES} defaultValue={workerData?.Status} onChange={handleIdentityChange} disabled={isSubmitting} />
                    </div>
                </div>

                {/* Certificate Section */}
                {!disableCertificates && (
                    <>
                        <h3 className="text-xl font-semibold text-gray-700 border-l-4 border-gray-400 pl-3 pt-6">Certificate Details</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-4 border rounded-lg bg-gray-50">
                            <div className="space-y-4">
                                <label className="text-sm font-medium text-gray-700">Certificate 1 Expiry Date:</label>
                                <div className="flex space-x-2">
                                    <SelectInput name="certificate1_year" options={YEAR_VALUES} defaultValue={cert1Date.year} onChange={(e) => handleCertDateChange(1, e)} />
                                    <SelectInput name="certificate1_month" options={MONTH_VALUES} defaultValue={cert1Date.month} onChange={(e) => handleCertDateChange(1, e)} />
                                    <SelectInput name="certificate1_day" options={DAY_VALUES} defaultValue={cert1Date.day} onChange={(e) => handleCertDateChange(1, e)} />
                                </div>
                                <label className="text-sm font-medium text-gray-700 pt-2">Certificate 2 Status (0=No, 1=Yes):</label>
                                <SelectInput name="Certificate2" options={CERTBOOL_VALUES} defaultValue={workerData?.Certificate2} onChange={handleIdentityChange} />
                            </div>
                            <div className="space-y-4">
                                <label className="text-sm font-medium text-gray-700">Certificate 3 Expiry Date:</label>
                                <div className="flex space-x-2">
                                    <SelectInput name="certificate3_year" options={YEAR_VALUES} defaultValue={cert3Date.year} onChange={(e) => handleCertDateChange(3, e)} />
                                    <SelectInput name="certificate3_month" options={MONTH_VALUES} defaultValue={cert3Date.month} onChange={(e) => handleCertDateChange(3, e)} />
                                    <SelectInput name="certificate3_day" options={DAY_VALUES} defaultValue={cert3Date.day} onChange={(e) => handleCertDateChange(3, e)} />
                                </div>
                                <label className="text-sm font-medium text-gray-700 pt-2">Certificate 4 Status (0=No, 1=Yes):</label>
                                <SelectInput name="Certificate4" options={CERTBOOL_VALUES} defaultValue={workerData?.Certificate4} onChange={handleIdentityChange} />
                            </div>
                        </div>
                    </>
                )}

                {/* Buttons */}
                <div className="flex justify-end space-x-4 pt-4">
                    <button type="button" onClick={closeModal} className="px-6 py-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 transition">Cancel</button>
                    <button type="submit" disabled={isSubmitting} className="px-6 py-2 bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 transition disabled:bg-gray-400">
                        {isSubmitting ? 'Saving...' : 'Save Changes'}
                    </button>
                </div>
            </form>
        </ModalOverlay>
    );
};

export default WorkerEditModal;
