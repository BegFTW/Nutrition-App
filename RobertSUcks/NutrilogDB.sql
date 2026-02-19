CREATE DATABASE IF NOT EXISTS NutriLog;
USE NutriLog;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS Meal_Log;
DROP TABLE IF EXISTS Workouts;
DROP TABLE IF EXISTS Users;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE Users (
    user_id INT PRIMARY KEY AUTO_INCREMENT,
    pass_key   VARCHAR(256) NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name  VARCHAR(50) NOT NULL
);

CREATE TABLE Meal_Log (
  log_id          INT PRIMARY KEY AUTO_INCREMENT,
  user_id         INT NOT NULL,
  calories_gained INT NULL,
  clock_time_meal DATETIME NULL,
  meal_items_json LONGTEXT NULL,
  CONSTRAINT fk_meal_user
    FOREIGN KEY (user_id)
    REFERENCES Users(user_id)
    ON DELETE CASCADE
);

CREATE TABLE Workouts (
    workout_id      INT PRIMARY KEY AUTO_INCREMENT,
    user_id         INT NOT NULL,
    workout_name    VARCHAR(50) NOT NULL,
    calories_burned INT NULL,
    CONSTRAINT fk_workouts_user
        FOREIGN KEY (user_id)
        REFERENCES Users(user_id)
        ON DELETE CASCADE
);

-- Demo user (keep your 2222)
INSERT INTO Users (user_id, pass_key, first_name, last_name)
VALUES (2222, '2222', 'Grace', 'Jonas');

-- Verify
SELECT DATABASE();
SHOW COLUMNS FROM Meal_Log;
SELECT * FROM Users;
