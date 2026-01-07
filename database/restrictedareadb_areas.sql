DROP TABLE IF EXISTS `Areas`;
CREATE TABLE `Areas` (
  `areaId` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  `parent_area_id` INT NULL DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`areaId`),
  UNIQUE KEY `name_UNIQUE` (`name`),
  KEY `fk_parent_area` (`parent_area_id`),
  CONSTRAINT `fk_parent_area` FOREIGN KEY (`parent_area_id`) REFERENCES `Areas` (`areaId`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;