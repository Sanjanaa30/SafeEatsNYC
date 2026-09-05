"""Explicit Spark schemas for SafeEats Bronze JSON and Silver type casts."""

from __future__ import annotations

from pyspark.sql.types import (
    ArrayType,
    DoubleType,
    StringType,
    StructField,
    StructType,
)


def string_schema(field_names: tuple[str, ...]) -> StructType:
    """Create nullable string fields because Socrata JSON stores values as text."""

    return StructType([StructField(name, StringType(), True) for name in field_names])


LOCATION_SCHEMA = StructType(
    [
        StructField("type", StringType(), True),
        StructField("coordinates", ArrayType(DoubleType()), True),
    ]
)


DOHMH_RAW_FIELDS = (
    "camis",
    "dba",
    "boro",
    "building",
    "street",
    "zipcode",
    "phone",
    "cuisine_description",
    "inspection_date",
    "action",
    "violation_code",
    "violation_description",
    "critical_flag",
    "score",
    "grade",
    "grade_date",
    "record_date",
    "inspection_type",
    "latitude",
    "longitude",
    "community_board",
    "council_district",
    "census_tract",
    "bin",
    "bbl",
    "nta",
)

DOHMH_RAW_SCHEMA = string_schema(DOHMH_RAW_FIELDS).add(
    StructField("location", LOCATION_SCHEMA, True)
)


COMPLAINT_311_RAW_FIELDS = (
    "unique_key",
    "created_date",
    "closed_date",
    "agency",
    "agency_name",
    "complaint_type",
    "descriptor",
    "descriptor_2",
    "location_type",
    "incident_zip",
    "incident_address",
    "street_name",
    "cross_street_1",
    "cross_street_2",
    "intersection_street_1",
    "intersection_street_2",
    "address_type",
    "city",
    "landmark",
    "facility_type",
    "status",
    "due_date",
    "resolution_description",
    "resolution_action_updated_date",
    "community_board",
    "council_district",
    "police_precinct",
    "bbl",
    "borough",
    "x_coordinate_state_plane",
    "y_coordinate_state_plane",
    "open_data_channel_type",
    "park_facility_name",
    "park_borough",
    "vehicle_type",
    "taxi_company_borough",
    "taxi_pick_up_location",
    "bridge_highway_name",
    "bridge_highway_direction",
    "road_ramp",
    "bridge_highway_segment",
    "latitude",
    "longitude",
)

COMPLAINT_311_RAW_SCHEMA = string_schema(COMPLAINT_311_RAW_FIELDS).add(
    StructField("location", LOCATION_SCHEMA, True)
)


# Cleaning uses these mappings to create typed Silver columns while retaining
# the original Bronze text for traceability and rejected-record reporting.
DOHMH_SILVER_CASTS = {
    "inspection_date": "timestamp",
    "grade_date": "timestamp",
    "record_date": "timestamp",
    "score": "integer",
    "latitude": "double",
    "longitude": "double",
}

COMPLAINT_311_SILVER_CASTS = {
    "created_date": "timestamp",
    "closed_date": "timestamp",
    "due_date": "timestamp",
    "resolution_action_updated_date": "timestamp",
    "x_coordinate_state_plane": "double",
    "y_coordinate_state_plane": "double",
    "latitude": "double",
    "longitude": "double",
}


def main() -> None:
    """Print a short, human-readable summary of the schema contract."""

    print(f"DOHMH Bronze fields: {len(DOHMH_RAW_SCHEMA.fields)}")
    print("DOHMH identifiers kept as strings: camis, zipcode, bin, bbl")
    print(f"DOHMH Silver casts: {DOHMH_SILVER_CASTS}")
    print(f"311 Bronze fields: {len(COMPLAINT_311_RAW_SCHEMA.fields)}")
    print("311 identifiers kept as strings: unique_key, incident_zip, bbl")
    print(f"311 Silver casts: {COMPLAINT_311_SILVER_CASTS}")
    print("Both location fields preserve point coordinates as doubles.")


if __name__ == "__main__":
    main()
