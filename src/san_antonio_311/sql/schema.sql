CREATE TABLE IF NOT EXISTS service_requests (
    srnumber text PRIMARY KEY,
    status text NOT NULL,
    location text,
    title text,
    department text,
    category text,
    cosa_tract_combo text,
    tract_name text,
    council_district smallint,
    median_household_income_rank integer,
    overall_rank integer,
    create_date timestamptz NOT NULL,
    due_date timestamptz,
    closed_date timestamptz,
    last_updated timestamptz NOT NULL,
    objectid bigint NOT NULL,
    xcoord double precision,
    ycoord double precision,
    longitude double precision,
    latitude double precision,
    coordinate_valid boolean NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT service_requests_status_not_blank CHECK (btrim(status) <> ''),
    CONSTRAINT service_requests_longitude_valid CHECK (
        longitude IS NULL OR longitude BETWEEN -180 AND 180
    ),
    CONSTRAINT service_requests_latitude_valid CHECK (
        latitude IS NULL OR latitude BETWEEN -90 AND 90
    )
);

CREATE INDEX IF NOT EXISTS service_requests_category_idx
    ON service_requests (category);

CREATE INDEX IF NOT EXISTS service_requests_status_idx
    ON service_requests (status);

CREATE INDEX IF NOT EXISTS service_requests_create_date_idx
    ON service_requests (create_date);
