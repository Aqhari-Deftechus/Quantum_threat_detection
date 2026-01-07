-- 1. Table for User Preferences
CREATE TABLE `NotificationPreferences` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NOT NULL,
  `email_enabled` BOOLEAN DEFAULT TRUE,
  `web_push_enabled` BOOLEAN DEFAULT TRUE,
  `anomaly_threshold` ENUM('all', 'medium_and_above', 'high_only') DEFAULT 'all',
  `digest_frequency` ENUM('realtime', 'hourly', 'daily', 'never') DEFAULT 'realtime',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_user_pref` (`user_id`),
  CONSTRAINT `fk_pref_user` FOREIGN KEY (`user_id`) REFERENCES `Users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Table for Notification History (Logs)
CREATE TABLE `NotificationLogs` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `anomaly_id` INT NULL, -- Optional link to an Anomaly
  `user_id` INT NOT NULL,
  `channel` ENUM('email', 'web_push', 'webhook') NOT NULL,
  `recipient` VARCHAR(255) NOT NULL,
  `subject` VARCHAR(255) NULL,
  `body` TEXT NULL,
  `status` ENUM('pending', 'sent', 'failed', 'delivered') DEFAULT 'pending',
  `sent_at` DATETIME NULL,
  `error_message` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_notif_user` (`user_id`),
  CONSTRAINT `fk_notif_user` FOREIGN KEY (`user_id`) REFERENCES `Users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;