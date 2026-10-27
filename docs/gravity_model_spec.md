# Gravity Model Calibration

## Target Mean Trip Distance

The baseline demand-weighted mean straight-line trip distance is set to **3,000 m**. This is a city-scale target: it allows trips across several central neighborhoods rather than concentrating demand almost entirely between adjacent stations. It is a modeling target, not a claim about observed MOL Bubi trips; it should be revisited when an observed trip-length distribution is available.

The previous default, $\beta = 0.0015\ \mathrm{m}^{-1}$, has an exponential distance scale of only

$$
1/\beta = 1/0.0015 \approx 667\ \mathrm{m}.
$$

That scale is too short for the intended city-scale demand model. In a two-dimensional city, the number of potential destinations in a thin ring grows approximately with its radius. With an exponential deterrence kernel, the radial distance density is therefore proportional to $r e^{-\beta r}$, whose mean is

$$
\frac{\int_0^\infty r^2 e^{-\beta r}\,dr}{\int_0^\infty r e^{-\beta r}\,dr}
= \frac{2}{\beta}.
$$

Thus a two-dimensional weighted mean is nearer $2/\beta$ than $1/\beta$. Setting that mean to the 3,000 m target gives

$$
\beta = \frac{2}{3,000\ \mathrm{m}}
= 0.0006666667\ \mathrm{m}^{-1}.
$$

`config/default_config.yaml` and the `generate_synthetic_trips` default both use this value. The generator normalizes the gravity weights to a total demand of $k$ times the population assigned to station catchments, and excludes same-station trips.

## Validation Results

The generated trip matrix's demand-weighted mean is calculated from its `trip_count` values and straight-line station distances.

| Dataset | Weighted mean distance | Result |
|---|---:|---|
| Synthetic 17 x 17 city grid, 1 km spacing | 2,812.4 m | 187.6 m below the 3,000 m target; within the test tolerance of +/-250 m |
| Committed sample fixtures | 1,160.6 m | Fixture-only diagnostic; its small and irregular extent is not expected to match the city target |

The grid result is below the infinite-plane approximation because the finite square has fewer available destinations near its boundaries. A city-data result is not yet available: `data/processed/population.parquet` has not been produced. Once it exists, run the same generator and weighted-mean calculation against the processed stations and population before treating the city calibration as verified.