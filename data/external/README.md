# External Weather Inputs

Place optional hourly weather files here when replacing the synthetic PV resource.

Supported lightweight inputs:

- NASA POWER hourly CSV with `YEAR,MO,DY,HR` and `ALLSKY_SFC_SW_DWN`; `T2M` is optional.
- ERA5 hourly CSV export with a time column and `ssrd` or `surface_solar_radiation_downwards`; `t2m` is optional.
- Generic hourly CSV with `timestamp` plus either `ghi_w_per_m2` or `pv_capacity_factor`.

NetCDF and GRIB are intentionally not read directly to keep the local Windows workflow limited to pandas, Pyomo, and HiGHS. Export ERA5 to CSV first.
