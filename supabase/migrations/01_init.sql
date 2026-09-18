-- =========================================
-- Script de creación de base de datos (versión simplificada)
-- Basado en el diagrama relacional EFICACIA (mini proyecto)
-- =========================================

CREATE TABLE e_user (
    u_id SERIAL PRIMARY KEY,
    u_name VARCHAR(100),
    last_name VARCHAR(100),
    daily_hours_l INT,
    u_type VARCHAR(50)
);

CREATE TABLE event (
    e_id SERIAL PRIMARY KEY,
    e_name VARCHAR(100),
    e_date DATE
);

CREATE TABLE task (
    t_id SERIAL PRIMARY KEY,
    d_date DATE,
    e_hours INT,
    name VARCHAR(100),
    description VARCHAR(500),
    state VARCHAR(50),
    e_id INT,
    g_id INT,
    type VARCHAR(20),
    FOREIGN KEY (e_id) REFERENCES event(e_id)
);

CREATE TABLE u_email (
    e_id SERIAL PRIMARY KEY,
    u_id INT,
    email VARCHAR(100),
    FOREIGN KEY (u_id) REFERENCES e_user(u_id)
);

CREATE TABLE u_phone (
    p_id SERIAL PRIMARY KEY,
    u_id INT,
    p_number VARCHAR(100),
    FOREIGN KEY (u_id) REFERENCES e_user(u_id)
);