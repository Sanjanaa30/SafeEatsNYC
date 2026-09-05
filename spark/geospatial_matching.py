"""Efficient nearest-restaurant matching for cleaned NYC 311 complaints."""

from __future__ import annotations

from pyspark.sql import DataFrame, Window, functions as F


EARTH_RADIUS_METERS = 6_371_008.8
GRID_SIZE_DEGREES = 0.002
DEFAULT_MATCH_THRESHOLD_METERS = 100.0


def current_restaurant_locations(inspections: DataFrame) -> DataFrame:
    """Return the newest valid location for each restaurant CAMIS."""

    valid = inspections.filter(
        F.col("camis").isNotNull()
        & F.col("latitude").isNotNull()
        & F.col("longitude").isNotNull()
        & (F.col("coordinate_status") == "VALID")
    )
    ordering = Window.partitionBy("camis").orderBy(
        F.col("record_date").desc_nulls_last(),
        F.col("inspection_date").desc_nulls_last(),
        F.col("inspection_violation_id").desc_nulls_last(),
    )
    return (
        valid.withColumn("_location_rank", F.row_number().over(ordering))
        .filter(F.col("_location_rank") == 1)
        .select(
            F.col("camis").alias("restaurant_camis"),
            F.col("restaurant_name_original").alias("matched_restaurant_name"),
            F.col("restaurant_name_normalized").alias(
                "matched_restaurant_name_normalized"
            ),
            F.col("address_display").alias("matched_restaurant_address"),
            F.col("latitude").alias("restaurant_latitude"),
            F.col("longitude").alias("restaurant_longitude"),
        )
    )


def haversine_distance_meters(
    first_latitude,
    first_longitude,
    second_latitude,
    second_longitude,
):
    """Return the great-circle distance between two coordinate pairs."""

    latitude_delta = F.radians(second_latitude - first_latitude)
    longitude_delta = F.radians(second_longitude - first_longitude)
    first_latitude_radians = F.radians(first_latitude)
    second_latitude_radians = F.radians(second_latitude)
    haversine_value = (
        F.pow(F.sin(latitude_delta / 2.0), 2)
        + F.cos(first_latitude_radians)
        * F.cos(second_latitude_radians)
        * F.pow(F.sin(longitude_delta / 2.0), 2)
    )
    safe_value = F.greatest(F.lit(0.0), F.least(F.lit(1.0), haversine_value))
    return F.lit(2.0 * EARTH_RADIUS_METERS) * F.asin(F.sqrt(safe_value))


def nearest_restaurant_matches(
    complaints: DataFrame,
    restaurants: DataFrame,
    threshold_meters: float = DEFAULT_MATCH_THRESHOLD_METERS,
) -> DataFrame:
    """Attach the nearest restaurant only when it is within the threshold."""

    if threshold_meters <= 0:
        raise ValueError("The match threshold must be greater than zero.")

    offsets = F.array(
        *[
            F.struct(F.lit(latitude).alias("lat"), F.lit(longitude).alias("lon"))
            for latitude in (-1, 0, 1)
            for longitude in (-1, 0, 1)
        ]
    )
    complaint_cells = (
        complaints.withColumn(
            "_latitude_cell",
            F.floor(F.col("latitude") / F.lit(GRID_SIZE_DEGREES)),
        )
        .withColumn(
            "_longitude_cell",
            F.floor(F.col("longitude") / F.lit(GRID_SIZE_DEGREES)),
        )
        .withColumn("_neighbor", F.explode(offsets))
        .withColumn(
            "_candidate_latitude_cell",
            F.col("_latitude_cell") + F.col("_neighbor.lat"),
        )
        .withColumn(
            "_candidate_longitude_cell",
            F.col("_longitude_cell") + F.col("_neighbor.lon"),
        )
    )
    restaurant_cells = (
        restaurants.withColumn(
            "_restaurant_latitude_cell",
            F.floor(F.col("restaurant_latitude") / F.lit(GRID_SIZE_DEGREES)),
        )
        .withColumn(
            "_restaurant_longitude_cell",
            F.floor(F.col("restaurant_longitude") / F.lit(GRID_SIZE_DEGREES)),
        )
    )

    candidates = complaint_cells.join(
        F.broadcast(restaurant_cells),
        (
            F.col("_candidate_latitude_cell")
            == F.col("_restaurant_latitude_cell")
        )
        & (
            F.col("_candidate_longitude_cell")
            == F.col("_restaurant_longitude_cell")
        ),
        "inner",
    ).withColumn(
        "nearest_candidate_distance_meters",
        haversine_distance_meters(
            F.col("latitude"),
            F.col("longitude"),
            F.col("restaurant_latitude"),
            F.col("restaurant_longitude"),
        ),
    )

    nearest_order = Window.partitionBy("unique_key").orderBy(
        F.col("nearest_candidate_distance_meters").asc(),
        F.col("restaurant_camis").asc(),
    )
    nearest = (
        candidates.withColumn("_nearest_rank", F.row_number().over(nearest_order))
        .filter(F.col("_nearest_rank") == 1)
        .select(
            "unique_key",
            "restaurant_camis",
            "matched_restaurant_name",
            "matched_restaurant_name_normalized",
            "matched_restaurant_address",
            "restaurant_latitude",
            "restaurant_longitude",
            "nearest_candidate_distance_meters",
        )
    )

    joined = complaints.join(nearest, "unique_key", "left")
    within_threshold = F.col("nearest_candidate_distance_meters") <= F.lit(
        float(threshold_meters)
    )
    restaurant_columns = (
        "restaurant_camis",
        "matched_restaurant_name",
        "matched_restaurant_name_normalized",
        "matched_restaurant_address",
        "restaurant_latitude",
        "restaurant_longitude",
    )
    for column_name in restaurant_columns:
        joined = joined.withColumn(
            column_name,
            F.when(within_threshold, F.col(column_name)),
        )
    return (
        joined.withColumn(
            "match_distance_meters",
            F.when(within_threshold, F.col("nearest_candidate_distance_meters")),
        )
        .withColumn(
            "restaurant_match_status",
            F.when(within_threshold, "MATCHED").otherwise(
                "NO_RESTAURANT_WITHIN_THRESHOLD"
            ),
        )
        .withColumn("match_threshold_meters", F.lit(float(threshold_meters)))
    )


def add_unmatched_nonspatial_complaints(
    matched_spatial: DataFrame,
    nonspatial: DataFrame,
    threshold_meters: float = DEFAULT_MATCH_THRESHOLD_METERS,
) -> DataFrame:
    """Union coordinate-less complaints back into the final valid dataset."""

    unmatched = (
        nonspatial.withColumn("restaurant_camis", F.lit(None).cast("string"))
        .withColumn("matched_restaurant_name", F.lit(None).cast("string"))
        .withColumn(
            "matched_restaurant_name_normalized", F.lit(None).cast("string")
        )
        .withColumn("matched_restaurant_address", F.lit(None).cast("string"))
        .withColumn("restaurant_latitude", F.lit(None).cast("double"))
        .withColumn("restaurant_longitude", F.lit(None).cast("double"))
        .withColumn(
            "nearest_candidate_distance_meters", F.lit(None).cast("double")
        )
        .withColumn("match_distance_meters", F.lit(None).cast("double"))
        .withColumn("restaurant_match_status", F.lit("NO_VALID_COORDINATES"))
        .withColumn("match_threshold_meters", F.lit(float(threshold_meters)))
    )
    return matched_spatial.unionByName(unmatched, allowMissingColumns=True)

