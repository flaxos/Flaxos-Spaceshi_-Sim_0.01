SECTOR_SIZE = 100000  # or whatever you use

def calculate_sector(pos):
    return (
        int(pos["x"] // SECTOR_SIZE),
        int(pos["y"] // SECTOR_SIZE),
        int(pos["z"] // SECTOR_SIZE),
    )
