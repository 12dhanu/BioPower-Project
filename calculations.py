
# BIOGAS AND POWER GENERATION CALCULATOR


# Estimated biogas yield for different waste types
WASTE_YIELDS = {
    "Food Waste": 0.10,
    "Cattle Dung": 0.04,
    "Agricultural Waste": 0.08,
    "Kitchen Waste": 0.12
}


# Default system assumptions
METHANE_PERCENTAGE = 60
GENERATOR_EFFICIENCY = 35
METHANE_ENERGY = 9.97


def calculate_generation(waste_type, waste_quantity):

    # Validate waste type
    if waste_type not in WASTE_YIELDS:
        raise ValueError("Invalid waste type selected.")

    # Validate quantity
    if waste_quantity <= 0:
        raise ValueError("Waste quantity must be greater than zero.")

    # Step 1: Calculate biogas production
    yield_value = WASTE_YIELDS[waste_type]

    biogas_volume = waste_quantity * yield_value

    # Step 2: Calculate methane volume
    methane_volume = (
        biogas_volume * METHANE_PERCENTAGE / 100
    )

    # Step 3: Calculate electricity generation
    electricity_generated = (
        methane_volume
        * METHANE_ENERGY
        * GENERATOR_EFFICIENCY / 100
    )

    # Step 4: Calculate remaining energy potential
    return {
        "waste_type": waste_type,
        "waste_quantity": round(waste_quantity, 2),
        "biogas_volume": round(biogas_volume, 2),
        "methane_percentage": METHANE_PERCENTAGE,
        "methane_volume": round(methane_volume, 2),
        "generator_efficiency": GENERATOR_EFFICIENCY,
        "electricity_generated": round(
            electricity_generated, 2
        )
    }


# Test the calculation program
if __name__ == "__main__":

    result = calculate_generation(
        "Food Waste",
        100
    )

    print("\nBIOGAS GENERATION RESULTS")
    print("------------------------")

    for key, value in result.items():
        print(key, ":", value)
