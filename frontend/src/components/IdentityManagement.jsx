import React, { useState, useEffect } from 'react';
import WorkerEditModal from './WorkerEditModal.jsx';

// API Endpoints
const API_WORKERS = "http://127.0.0.1:8000/workers";
const API_ME = "http://127.0.0.1:8000/me";
const API_DELETE_WORKER = (id) => `http://127.0.0.1:8000/worker/delete/${id}`;

const IdentityManagement = ({ setCurrentPage, currentUser }) => {
    const [workers, setWorkers] = useState([]);
    const [filteredWorkers, setFilteredWorkers] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [workerToDelete, setWorkerToDelete] = useState(null);
    const [workerToEdit, setWorkerToEdit] = useState(null);

    // State to track the active role displayed in UI
    const [activeRole, setActiveRole] = useState(currentUser?.role || localStorage.getItem('role') || 'Unknown');

    // --- EFFECT: SYNC ROLE WITH DB ---
    // This fixes the issue where localStorage might say "Admin" but DB says "SuperAdmin"
    useEffect(() => {
        const syncRole = async () => {
            const token = localStorage.getItem('authToken');
            if (!token) return;

            try {
                const response = await fetch(API_ME, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (response.ok) {
                    const data = await response.json();
                    if (data.role && data.role !== activeRole) {
                        console.log(`Role mismatch detected. Updating from ${activeRole} to ${data.role}`);
                        localStorage.setItem('role', data.role);
                        setActiveRole(data.role);
                    }
                }
            } catch (e) {
                console.warn("Failed to sync role in background", e);
            }
        };
        syncRole();
    }, []); // Run once on mount

    const isSuperAdmin = activeRole === 'SuperAdmin';

    // --- FETCH WORKERS ---
    const fetchWorkers = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const token = localStorage.getItem('authToken');
            if (!token) throw new Error("Authentication missing. Please Logout and Sign In again.");

            const response = await fetch(API_WORKERS, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });

            if (response.status === 401) throw new Error("Session expired. Please Logout and Sign In again.");
            if (!response.ok) throw new Error(`Failed to fetch workers: ${response.statusText}`);

            const data = await response.json();
            data.sort((a, b) => (a.PersonName || "").localeCompare(b.PersonName || ""));
            setWorkers(data);
            setFilteredWorkers(data);
        } catch (err) {
            console.error("Fetch Error:", err);
            setError(err.message);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => { fetchWorkers(); }, []);

    // Handle Search
    useEffect(() => {
        if (searchTerm.trim() === '') {
            setFilteredWorkers(workers);
            return;
        }
        const lowerCaseSearch = searchTerm.toLowerCase();
        const results = workers.filter(worker =>
            (worker.PersonName && worker.PersonName.toLowerCase().includes(lowerCaseSearch)) ||
            (worker.BadgeID && worker.BadgeID.toLowerCase().includes(lowerCaseSearch)) ||
            (worker.Department && worker.Department.toLowerCase().includes(lowerCaseSearch))
        );
        setFilteredWorkers(results);
    }, [searchTerm, workers]);

    const handleDeleteConfirmation = (worker) => { setWorkerToDelete(worker); };

    const deleteWorker = async () => {
        if (!workerToDelete) return;
        setIsLoading(true);
        setError(null);
        try {
            const token = localStorage.getItem('authToken');
            if (!token) throw new Error("No token found");

            const response = await fetch(API_DELETE_WORKER(workerToDelete.BadgeID), {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
            });

            if (response.status === 401) throw new Error("Session expired. Please Logout and Sign In again.");
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || "Deletion failed.");
            }
            await fetchWorkers();
            setWorkerToDelete(null);
            alert(`✅ Successfully deleted worker: ${workerToDelete.PersonName}`);
        } catch (err) {
            console.error("Delete Error:", err);
            setError(`Deletion failed: ${err.message}`);
        } finally {
            setIsLoading(false);
        }
    };

    // UI Formatters
    const getCertStatus = (certBool) => {
        const status = String(certBool);
        return status === '1' ?
            <span className="text-xs bg-green-100 text-green-800 p-1 rounded-full font-semibold">Valid</span> :
            <span className="text-xs bg-red-100 text-red-800 p-1 rounded-full font-semibold">Missing</span>;
    };

    const formatDate = (dateString) => {
        if (!dateString || dateString === 'N/A' || dateString.startsWith('2035'))
            return <span className="text-gray-400">N/A</span>;

        const date = new Date(dateString);
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0'); // months are 0-indexed
        const year = date.getFullYear();

        const formatted = `${day}/${month}/${year}`;
        return <span className="font-mono text-gray-700">{formatted}</span>;
    }

    const tableContent = filteredWorkers.length > 0 ? (
        <div className="overflow-x-auto shadow-md rounded-lg border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                    <tr>
                        <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Identity</th>
                        <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Role</th>
                        <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Access</th>
                        <th className="px-6 py-3 text-center text-xs font-bold text-gray-500 uppercase tracking-wider">Cert 1</th>
                        <th className="px-6 py-3 text-center text-xs font-bold text-gray-500 uppercase tracking-wider">Cert 2</th>
                        <th className="px-6 py-3 text-center text-xs font-bold text-gray-500 uppercase tracking-wider">Cert 3</th>
                        <th className="px-6 py-3 text-center text-xs font-bold text-gray-500 uppercase tracking-wider">Cert 4</th>
                        <th className="px-6 py-3 text-right text-xs font-bold text-gray-500 uppercase tracking-wider">Actions</th>
                    </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                    {filteredWorkers.map((worker) => (
                        <tr key={worker.BadgeID} className="hover:bg-blue-50 transition duration-150">
                            <td className="px-6 py-4 whitespace-nowrap">
                                <div className="text-sm font-bold text-gray-900">{worker.PersonName}</div>
                                <div className="text-xs text-gray-500 font-mono">{worker.BadgeID}</div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                                <div className="text-sm text-gray-900">{worker.Position}</div>
                                <div className="text-xs text-blue-600 font-semibold">{worker.Department}</div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                                <span className={`px-2 py-0.5 inline-flex text-xs leading-5 font-bold rounded-full
                                    ${['Admin','SuperAdmin'].includes(worker.AccessLevel) ? 'bg-purple-100 text-purple-800' :
                                      (worker.AccessLevel === 'Visitor' ? 'bg-yellow-100 text-yellow-800' : 'bg-green-100 text-green-800')}`}>
                                    {worker.AccessLevel}
                                </span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm text-center">{formatDate(worker.Certificate1)}</td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm text-center">{getCertStatus(String(worker.Certificate2))}</td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm text-center">{formatDate(worker.Certificate3)}</td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm text-center">{getCertStatus(String(worker.Certificate4))}</td>
                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium space-x-2">
                                <button onClick={() => setWorkerToEdit(worker.BadgeID)} className="text-indigo-600 hover:text-indigo-900 font-semibold hover:underline">Edit</button>
                                {isSuperAdmin ? (
                                    <button onClick={() => handleDeleteConfirmation(worker)} className="text-red-600 hover:text-red-900 font-semibold hover:underline">Delete</button>
                                ) : (
                                    <span className="text-gray-300 text-xs cursor-not-allowed" title="SuperAdmin only">Delete</span>
                                )}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    ) : (
        <div className="text-center p-12 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300 text-gray-500">
            {isLoading ? "Loading secure database..." : "No active employees found matching your search."}
        </div>
    );

    return (
        <div className="max-w-7xl mx-auto mt-10 p-8 bg-white rounded-xl shadow-xl">
            <div className="flex justify-between items-center mb-6">
                <button onClick={() => setCurrentPage('Home')} className="text-gray-500 hover:text-gray-800 flex items-center transition duration-150 font-medium">
                    &larr; Dashboard
                </button>
                <div className="text-right">
                    <h2 className="text-2xl font-bold text-gray-800">Identity Management</h2>
                    <div className="flex items-center justify-end gap-2 text-sm text-gray-500">
                        <span>Total Records: {workers.length}</span>
                        <span className="text-gray-300">|</span>
                        <span className={`font-mono text-xs px-2 py-0.5 rounded-full ${isSuperAdmin ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'}`}>
                            Current Role: {activeRole}
                        </span>
                        {/* {!isSuperAdmin && (
                            <span className="text-xs text-orange-500 italic ml-2">(Edit your profile below to promote)</span>
                        )} */}
                    </div>
                </div>
            </div>

            <div className="relative mb-6">
                <input type="text" placeholder="Search by Name, Badge ID, or Department..." value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} className="w-full p-4 pl-12 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 shadow-sm transition" />
                <span className="absolute left-4 top-4 text-gray-400">🔍</span>
            </div>

            {error && (
                <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-6 rounded-r-lg flex justify-between items-center">
                    <div><p className="font-bold text-red-700">Access Error</p><p className="text-sm text-red-600">{error}</p></div>
                    {(error.includes("expired") || error.includes("missing")) && (<button onClick={() => window.location.reload()} className="text-xs bg-red-100 hover:bg-red-200 text-red-800 px-3 py-1 rounded">Reload App</button>)}
                </div>
            )}

            {tableContent}

            {workerToDelete && (
                <div className="fixed inset-0 bg-gray-900 bg-opacity-75 flex items-center justify-center z-50 backdrop-blur-sm">
                    <div className="bg-white p-8 rounded-2xl shadow-2xl max-w-sm w-full transform transition-all scale-100">
                        <h3 className="text-xl font-bold text-red-600 mb-4 flex items-center gap-2">⚠️ Confirm Deletion</h3>
                        <p className="text-gray-700 mb-6">Are you sure you want to delete <strong>{workerToDelete.PersonName}</strong>? This cannot be undone.</p>
                        <div className="flex justify-end space-x-3">
                            <button onClick={() => setWorkerToDelete(null)} className="px-5 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition">Cancel</button>
                            <button onClick={deleteWorker} disabled={isLoading} className="px-5 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition">{isLoading ? 'Deleting...' : 'Yes, Delete'}</button>
                        </div>
                    </div>
                </div>
            )}

            {workerToEdit && (
                <WorkerEditModal badgeID={workerToEdit} closeModal={() => setWorkerToEdit(null)} onUpdateSuccess={() => { setWorkerToEdit(null); fetchWorkers(); }} />
            )}
        </div>
    );
};

export default IdentityManagement;