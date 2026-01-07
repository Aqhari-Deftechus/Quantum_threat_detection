CREATE TABLE `AttendanceRecords` (
  `ar_id` INT NOT NULL AUTO_INCREMENT,
  `employee_id` VARCHAR(30) NOT NULL,
  `event_type` ENUM('clock_in', 'clock_out') NOT NULL,
  `timestamp` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last_seen',
  `confidence_score` FLOAT DEFAULT NULL,
  `snapshot_url` VARCHAR(255) DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`ar_id`),
  KEY `idx_emp_timestamp` (`employee_id`, `timestamp`),
  CONSTRAINT `fk_attendance_employee` FOREIGN KEY (`employee_id`) REFERENCES `WorkerIdentity` (`employee_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;