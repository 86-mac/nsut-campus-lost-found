CREATE DATABASE IF NOT EXISTS campus_lost_found CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE campus_lost_found;

CREATE TABLE IF NOT EXISTS users (
  user_id INT AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL UNIQUE,
  roll_no VARCHAR(30) NULL UNIQUE,
  role ENUM('student','admin') NOT NULL DEFAULT 'student',
  password_hash VARCHAR(255) NOT NULL,
  profile_image_path VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS categories (
  category_id INT AUTO_INCREMENT PRIMARY KEY,
  category_name VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS locations (
  location_id INT AUTO_INCREMENT PRIMARY KEY,
  location_name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS items (
  item_id INT AUTO_INCREMENT PRIMARY KEY,
  report_type ENUM('Lost','Found') NOT NULL,
  item_name VARCHAR(120) NOT NULL,
  category_id INT NOT NULL,
  location_id INT NOT NULL,
  description TEXT NULL,
  item_date DATE NOT NULL,
  reporter_id INT NOT NULL,
  status ENUM('Open','Claimed','Returned','Resolved') NOT NULL DEFAULT 'Open',
  image_path VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_items_category FOREIGN KEY(category_id) REFERENCES categories(category_id),
  CONSTRAINT fk_items_location FOREIGN KEY(location_id) REFERENCES locations(location_id),
  CONSTRAINT fk_items_reporter FOREIGN KEY(reporter_id) REFERENCES users(user_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS claims (
  claim_id INT AUTO_INCREMENT PRIMARY KEY,
  item_id INT NOT NULL,
  claimant_id INT NOT NULL,
  claim_date DATE NOT NULL,
  claim_status ENUM('Pending','Approved','Rejected') NOT NULL DEFAULT 'Pending',
  CONSTRAINT fk_claim_item FOREIGN KEY(item_id) REFERENCES items(item_id) ON DELETE CASCADE,
  CONSTRAINT fk_claim_user FOREIGN KEY(claimant_id) REFERENCES users(user_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS notifications (
  notification_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  message VARCHAR(500) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT fk_notification_user FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS item_tracking (
  tracking_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  item_id INT NOT NULL,
  actor_id INT NULL,
  event VARCHAR(100) NOT NULL,
  details VARCHAR(500) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_tracking_item FOREIGN KEY(item_id) REFERENCES items(item_id) ON DELETE CASCADE,
  CONSTRAINT fk_tracking_actor FOREIGN KEY(actor_id) REFERENCES users(user_id) ON DELETE SET NULL,
  INDEX idx_tracking_item_time (item_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS password_resets (
  reset_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  token_hash VARCHAR(255) NOT NULL,
  expires_at DATETIME NOT NULL,
  used_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_reset_user FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  INDEX idx_reset_user (user_id), INDEX idx_reset_expiry (expires_at)
) ENGINE=InnoDB;

-- Give items created before tracking was added a starting timeline entry.
INSERT INTO item_tracking(item_id, actor_id, event, details, created_at)
SELECT i.item_id, i.reporter_id, 'Existing record',
       CONCAT('Tracking history enabled. Current item status: ', i.status, '.'),
       i.created_at
FROM items i
WHERE NOT EXISTS (SELECT 1 FROM item_tracking t WHERE t.item_id=i.item_id);

-- Safe upgrades for an existing database created by the earlier project version.
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_image_path VARCHAR(255) NULL;
ALTER TABLE items ADD COLUMN IF NOT EXISTS image_path VARCHAR(255) NULL;

INSERT IGNORE INTO categories(category_name) VALUES
('Electronics'),('Books & Stationery'),('ID & Cards'),('Clothing'),('Bags'),('Keys'),('Wallet & Money'),('Accessories'),('Other');
INSERT IGNORE INTO locations(location_name) VALUES
('APJ Complex'),('Block:-5'),('Block:-6'),('Nesci Lawn'),('Ramanujan Hostel'),
('Raman Hostel'),('Bhaskar Hostel'),('Aryabhata Hostel'),('JC Bose'),
('Saraswati Hostel'),('Kaveri Hostel'),('North Gate');

CREATE OR REPLACE VIEW v_items AS
SELECT i.item_id, i.report_type, i.item_name, c.category_name, l.location_name,
       i.description, i.item_date, u.full_name AS reporter, u.email AS reporter_email,
       i.status, i.image_path
FROM items i JOIN categories c ON c.category_id=i.category_id
JOIN locations l ON l.location_id=i.location_id JOIN users u ON u.user_id=i.reporter_id;
