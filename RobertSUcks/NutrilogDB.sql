CREATE DATABASE IF NOT EXISTS NutriLog;
USE NutriLog;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS Social_Post_Tags;
DROP TABLE IF EXISTS Social_Comments;
DROP TABLE IF EXISTS Social_Posts;
DROP TABLE IF EXISTS Meal_Log;
DROP TABLE IF EXISTS Workouts;
DROP TABLE IF EXISTS Users;
DROP TABLE IF EXISTS Social_Follows;
DROP TABLE IF EXISTS Social_Post_Likes;
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

CREATE TABLE Social_Posts (
    post_id         INT PRIMARY KEY AUTO_INCREMENT,
    user_id         INT NOT NULL,
    posts_json      LONGTEXT NOT NULL,
    location_name   VARCHAR(255) NULL,
    image_filename  VARCHAR(255) NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_social_posts_user
        FOREIGN KEY (user_id)
        REFERENCES Users(user_id)
        ON DELETE CASCADE
);

CREATE TABLE Social_Comments (
    comment_id    INT PRIMARY KEY AUTO_INCREMENT,
    post_id       INT NOT NULL,
    user_id       INT NOT NULL,
    comment_text  LONGTEXT NOT NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_comments_post
        FOREIGN KEY (post_id)
        REFERENCES Social_Posts(post_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_comments_user
        FOREIGN KEY (user_id)
        REFERENCES Users(user_id)
        ON DELETE CASCADE
);

CREATE TABLE Social_Post_Tags (
    post_id            INT NOT NULL,
    tagged_user_id     INT NOT NULL,
    tagged_by_user_id  INT NOT NULL,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (post_id, tagged_user_id),
    CONSTRAINT fk_tags_post
        FOREIGN KEY (post_id)
        REFERENCES Social_Posts(post_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_tags_tagged_user
        FOREIGN KEY (tagged_user_id)
        REFERENCES Users(user_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_tags_by_user
        FOREIGN KEY (tagged_by_user_id)
        REFERENCES Users(user_id)
        ON DELETE CASCADE
);

CREATE TABLE Social_Follows (
    follower_user_id  INT NOT NULL,
    followed_user_id  INT NOT NULL,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (follower_user_id, followed_user_id),
    CONSTRAINT fk_follows_follower
        FOREIGN KEY (follower_user_id)
        REFERENCES Users(user_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_follows_followed
        FOREIGN KEY (followed_user_id)
        REFERENCES Users(user_id)
        ON DELETE CASCADE,
    CONSTRAINT chk_no_self_follow
        CHECK (follower_user_id <> followed_user_id)
);

CREATE TABLE Social_Post_Likes (
    post_id     INT NOT NULL,
    user_id     INT NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (post_id, user_id),
    CONSTRAINT fk_likes_post
        FOREIGN KEY (post_id)
        REFERENCES Social_Posts(post_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_likes_user
        FOREIGN KEY (user_id)
        REFERENCES Users(user_id)
        ON DELETE CASCADE
);

INSERT INTO Users (user_id, pass_key, first_name, last_name)
VALUES (2222, '2222', 'Grace', 'Jonas');

INSERT INTO Users (user_id, pass_key, first_name, last_name)
VALUES (3333, '3333', 'Tyler', 'Cole');

SELECT DATABASE();
SHOW COLUMNS FROM Social_Posts;
SHOW COLUMNS FROM Social_Comments;
SHOW COLUMNS FROM Social_Post_Tags;
SELECT * FROM Users;