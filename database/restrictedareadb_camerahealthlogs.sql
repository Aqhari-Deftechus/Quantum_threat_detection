DROP TABLE IF EXISTS `CameraHealthLogs`;
CREATE TABLE `CameraHealthLogs` (
  `ch_id` INT NOT NULL AUTO_INCREMENT,
  `camera_id` INT NOT NULL,
  `status` ENUM('online', 'offline', 'error') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `checked_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `response_time_ms` INT DEFAULT 0,
  `error_details` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  PRIMARY KEY (`ch_id`),
  KEY `idx_camera_checked` (`camera_id`, `checked_at`),
  CONSTRAINT `fk_health_camera` FOREIGN KEY (`camera_id`) REFERENCES `Cameras` (`cameraId`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;