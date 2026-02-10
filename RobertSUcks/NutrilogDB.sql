CREATE DATABASE IF NOT EXISTS NutriLog;
USE Nutrilog;

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS Meal_Log;
DROP TABLE IF EXISTS Users;
DROP TABLE IF EXISTS Workouts;

SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE Users (
    user_id INT PRIMARY KEY AUTO_INCREMENT,
    pass_key   VARCHAR(50) NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name  VARCHAR(50) NOT NULL
);

CREATE TABLE Meal_Log (
    log_id                    INT PRIMARY KEY AUTO_INCREMENT,
    user_id                   INT NOT NULL,
    calories_gained           INT,
    clock_time_meal           DATETIME NULL,          -- Stores date + 24-hour time
    CONSTRAINT fk_meal_user
        FOREIGN KEY (user_id)
        REFERENCES Users(user_id)
        ON DELETE CASCADE
);

CREATE TABLE Workouts (
    workout_id   INT PRIMARY KEY AUTO_INCREMENT,
    user_id      INT NOT NULL,
    workout_name VARCHAR(50) NOT NULL,
    calories_burned           INT,
    CONSTRAINT fk_assign_student
        FOREIGN KEY (user_id)
        REFERENCES Users(user_id)
        ON DELETE CASCADE
);

INSERT INTO Users (user_id, pass_key, first_name, last_name)
VALUES (2222, '2222', 'Grace', 'Jonas');

INSERT INTO Meal_Log (log_id, user_id, calories_gained, clock_time_meal)
VALUES (0001, 2222, NULL, NULL);

INSERT INTO Workouts (user_id, workout_id, workout_name, calories_burned)
VALUES (2222, 1000, 'Chest Press', 92);
 