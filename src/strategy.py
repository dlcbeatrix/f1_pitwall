from src.calibration import FUEL_EFFECT
from itertools import product

def simulate_strategy(strategy: list, base_pace: float, compound_params: dict, pit_loss: float, fuel_effect: float = FUEL_EFFECT,
                      knee_ages: dict | None = None, cliff_slope: float = 0.0)->list:
    """Lap times (seconds) of a strategy.
    Strategy = list of compound and number of laps, e.g. [("SOFT", 15), ("HARD", 33)]"""
    
    lap_times = []
    lap_number = 0
    
    for stint_index, (compound, stint_laps) in enumerate(strategy):
        params = compound_params[compound]
        
        knee = None
        if knee_ages is not None: 
            knee = knee_ages.get(compound)
            
        for tyre_age in range(1, stint_laps + 1):
            lap_number += 1
            lap_time = (base_pace + params["offset"] + params["degradation"]*tyre_age - fuel_effect* lap_number)
        
            if knee is not None and tyre_age > knee: 
                lap_time += cliff_slope * (tyre_age-knee)
            
            lap_times.append(lap_time)
        
        is_last_stint = stint_index == len(strategy)-1
        if not is_last_stint: 
            lap_times[-1] += pit_loss
    return lap_times

def generate_sequences(compounds: list, max_stops: int = 2)->list: 
    """All compound sequences with 1 to max_stops stops, using at least 2 different compounds"""
    sequences = []
    for n_stints in range(2, max_stops+2):
        for sequence in product(compounds, repeat = n_stints):
            if len(set(sequence)) >=2 :
                sequences.append(sequence)
    return sequences

def generate_strategies(compounds: list, total_laps: int, max_stops: int = 2, min_stint_laps: int = 8) -> list: 
    """Generates complete strategies with compounds and number of laps for every stint"""
    
    strategies = []
    sequences = generate_sequences(compounds, max_stops)
    
    for sequence in sequences: 
        stint_count = len(sequence)
        
        if total_laps < stint_count * min_stint_laps: 
            continue
        
        if stint_count == 2: 
            for first_stint_laps in range(min_stint_laps, total_laps-min_stint_laps+1):
                second_stint_laps = total_laps-first_stint_laps
                
                strategies.append([(sequence[0], first_stint_laps), 
                                   (sequence[1], second_stint_laps)
                                ])
        
        elif stint_count == 3: 
            for first_stint_laps in range(min_stint_laps, total_laps - 2 * min_stint_laps + 1):
                for second_stint_laps in range(min_stint_laps, total_laps - first_stint_laps - min_stint_laps + 1):
                    third_stint_laps = (total_laps- first_stint_laps- second_stint_laps)

                    strategies.append([
                        (sequence[0], first_stint_laps),
                        (sequence[1], second_stint_laps),
                        (sequence[2], third_stint_laps),
                    ])

    return strategies
                
    