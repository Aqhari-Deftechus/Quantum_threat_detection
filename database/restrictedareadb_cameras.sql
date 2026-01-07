DROP TABLE IF EXISTS `Cameras`;
CREATE TABLE `Cameras` (
  `cameraId` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `rtsp_url` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `areaId` INT NULL DEFAULT NULL,
  `location_description` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  `camera_type` ENUM('entrance', 'exit', 'zone', 'ppe_check') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `resolution` VARCHAR(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT '1080p',
  `fps` INT DEFAULT 15,
  `is_active` BOOLEAN DEFAULT TRUE,
  `status` ENUM('online', 'offline', 'error', 'maintenance') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'offline',
  `last_health_check_at` DATETIME NULL DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`cameraId`),
  UNIQUE KEY `name_UNIQUE` (`name`),
  KEY `fk_camera_area` (`areaId`),
  CONSTRAINT `fk_camera_area` FOREIGN KEY (`areaId`) REFERENCES `Areas` (`areaId`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;