# solarcontrol


## Goals

### Production Maximizing by Adding Load
- detect when there's excess solar potential that's not being used
- activate the EVSE 
- adjust EVSE charging rate to avoid grid import
- adjust every one minute ?duration?
- send a note that there's excess production to encourage using more power (like doing laundry)

### Off-peak battery charge rate optimization
- if the next day is likely to be high production, then don't charge the battery as much overnight (off-peak)

### Prepper Mode
- switch battery to force-charge ???
- switch to backup mode after charge is 100%
- toggle switch, pushbutton or web control panel



## Notes

### Flow
- battery_to_grid -- negative = charging
- grid_to_load -- negative = exporting **should not happen**

