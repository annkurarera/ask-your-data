-- 01_schema.sql: loan_portfolio table (synthetic BFSI loan book, snapshot 2026-09-30)

DROP TABLE IF EXISTS loan_portfolio;

CREATE TABLE loan_portfolio (
    loan_id                VARCHAR(12)   PRIMARY KEY,
    customer_id            VARCHAR(12)   NOT NULL,
    customer_age           SMALLINT      NOT NULL,
    gender                 VARCHAR(10)   NOT NULL,
    occupation             VARCHAR(20)   NOT NULL,
    annual_income          BIGINT        NOT NULL,
    cibil_score            SMALLINT,                 -- NULL = new-to-credit
    branch_code            VARCHAR(8)    NOT NULL,
    city                   VARCHAR(30)   NOT NULL,
    state                  VARCHAR(30)   NOT NULL,
    region                 VARCHAR(12)   NOT NULL,
    city_tier              VARCHAR(8)    NOT NULL,
    product_type           VARCHAR(30)   NOT NULL,
    is_secured             BOOLEAN       NOT NULL,
    channel                VARCHAR(10)   NOT NULL,
    disbursement_date      DATE          NOT NULL,
    sanctioned_amount      BIGINT        NOT NULL,
    disbursed_amount       BIGINT        NOT NULL,
    interest_rate          NUMERIC(5,2)  NOT NULL,
    tenure_months          SMALLINT      NOT NULL,
    emi_amount             BIGINT        NOT NULL,
    collateral_type        VARCHAR(40)   NOT NULL,
    collateral_value       BIGINT,                   -- NULL for unsecured
    ltv_ratio              NUMERIC(6,4),             -- NULL for unsecured
    emis_paid              SMALLINT      NOT NULL,
    outstanding_principal  NUMERIC(14,2) NOT NULL,
    overdue_amount         NUMERIC(14,2) NOT NULL,
    dpd                    INTEGER       NOT NULL,
    asset_classification   VARCHAR(15),              -- NULL for closed loans
    loan_status            VARCHAR(12)   NOT NULL,
    npa_date               DATE,
    closure_date           DATE,
    last_payment_date      DATE
);
