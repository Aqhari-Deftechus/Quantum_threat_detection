CREATE TABLE `PushSubscriptions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NOT NULL, -- Links to the Users table (Admins/Guards)
  `endpoint` TEXT NOT NULL, -- The unique URL from the browser push service
  `p256dh` VARCHAR(255) NOT NULL, -- Encryption key
  `auth` VARCHAR(255) NOT NULL, -- Authentication secret
  `user_agent` VARCHAR(255) NULL, -- To track if it's Chrome, Firefox, Mobile, etc.
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_push_user` (`user_id`),
  CONSTRAINT `fk_push_user` FOREIGN KEY (`user_id`) REFERENCES `Users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;