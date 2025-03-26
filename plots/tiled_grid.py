#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib",
# ]
# ///


import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

def create_color_palette(base_color, num_colors=16, min_intensity=0.4, max_intensity=1.0):
    """
    Create a custom color palette with varying intensities of the base color.
    
    Parameters:
    -----------
    base_color : str or tuple
        The base color to create shades from (e.g., 'green', 'red', etc.)
    num_colors : int
        Number of colors to create
    min_intensity : float
        Minimum intensity for the lightest color (between 0 and 1)
    max_intensity : float
        Maximum intensity for the darkest color (between 0 and 1)
        
    Returns:
    --------
    list of colors (rgba)
    """
    # Convert string color to rgb
    if isinstance(base_color, str):
        base_rgb = mcolors.to_rgb(base_color)
    else:
        base_rgb = base_color
    
    # Create a list of colors with varying intensity
    colors = []
    for i in range(num_colors):
        # Scale intensity from min to max
        intensity = min_intensity + (max_intensity - min_intensity) * (i / (num_colors - 1))
        # Create color with adjusted intensity
        color = tuple(min(1.0, c * intensity) for c in base_rgb) + (1.0,)  # Add alpha=1.0
        colors.append(color)
    colors.reverse()
    return colors

colors = [
    ["#57bb8a", "#61bf91", "#6ac397", "#73c79e", "#e67c73", "#e8847b", "#e98b83", "#eb938b"],
    ["#7ccba4", "#85ceaa", "#8ed2b1", "#97d6b7", "#ec9a93", "#eda19b", "#efa9a3", "#f0b0ab"],
    ["#a0dabe", "#a9dec4", "#b2e1ca", "#bbe5d1", "#f2b8b3", "#f3bfbb", "#f4c6c3", "#f6cecb"],
    ["#c4e9d7", "#cdedde", "#d6f1e4", "#dff4ea", "#f7d5d3", "#f9dddb", "#fae4e3", "#fbebeb"],
    ["#3d85c6", "#498dca", "#5494ce", "#5f9bd1", "#ffd666", "#ffd96f", "#ffdb77", "#ffdd7f"],
    ["#6aa2d5", "#75a9d8", "#80b0dc", "#8bb7df", "#ffe088", "#ffe290", "#ffe498", "#ffe6a1"],
    ["#96bfe3", "#a1c6e6", "#accdea", "#b7d4ed", "#ffe9a9", "#ffebb1", "#ffedba", "#ffefc2"],
    ["#c2dbf1", "#cde2f4", "#d8e9f8", "#e3f0fb", "#fff2ca", "#fff4d3", "#fff6db", "#fff8e3"]
]

def hex_to_rgba(hex_color):
    res =  tuple(c for c in mcolors.to_rgba(hex_color))
    assert len(res) == 4, hex_color
    return res

tiles = {
    "top_left": [hex_to_rgba(colors[r][c]) for r in range(4) for c in range(4)],
    "top_right": [hex_to_rgba(colors[r][c]) for r in range(4) for c in range(4, 8)],
    "bottom_left": [hex_to_rgba(colors[r][c]) for r in range(4, 8) for c in range(4)],
    "bottom_right": [hex_to_rgba(colors[r][c]) for r in range(4, 8) for c in range(4, 8)]
}


def get_palette_set(palettes_config=None):
    """
    Get a set of color palettes based on the provided configuration.
    This function can be customized later to return different palette sets.
    
    Parameters:
    -----------
    palettes_config : dict or None
        Configuration for the palettes. If None, uses default settings.
        
    Returns:
    --------
    Dictionary of color palettes
    """
    # Default palette configuration
    if palettes_config is None:
        palettes_config = {
        }
    return tiles
    return {
    'top_left': [  # Green tile (top-left)
        (115, 196, 156), (111, 195, 154), (119, 198, 159), (127, 202, 165),
        (138, 206, 173), (136, 205, 171), (146, 209, 178), (153, 213, 183),
        (170, 220, 196), (171, 221, 196), (180, 225, 203), (189, 228, 210),
        (188, 224, 215), (191, 226, 218), (200, 230, 224), (209, 233, 230)
    ],
    'top_right': [  # Red tile (top-right)
        (229, 136, 128), (231, 143, 135), (232, 149, 142), (235, 160, 153),
        (234, 157, 150), (235, 163, 158), (237, 172, 166), (238, 180, 175),
        (240, 186, 181), (241, 192, 189), (243, 200, 197), (245, 209, 206),
        (245, 212, 199), (247, 220, 208), (248, 226, 216), (249, 233, 224)
    ],
    'bottom_left': [  # Blue tile (bottom-left)
        (89, 150, 204), (85, 148, 204), (95, 154, 208), (106, 161, 211),
        (129, 175, 217), (127, 175, 217), (139, 182, 222), (148, 188, 224),
        (167, 200, 230), (169, 202, 231), (181, 210, 235), (191, 216, 238),
        (209, 226, 242), (214, 230, 244), (222, 236, 247), (231, 241, 250)
    ],
    'bottom_right': [  # Yellow tile (bottom-right)
        (252, 215, 112), (253, 218, 120), (253, 220, 128), (253, 223, 141),
        (252, 224, 145), (253, 226, 152), (253, 229, 161), (253, 231, 171),
        (252, 233, 176), (253, 235, 183), (253, 237, 193), (253, 240, 202),
        (252, 242, 212), (253, 244, 219), (253, 246, 225), (253, 247, 232)
    ]
}

    palettes = {}
    for position, config in palettes_config.items():
        palettes[position] = create_color_palette(
            config['color'], 
            num_colors=16,
            min_intensity=config.get('min_intensity', 0.1),
            max_intensity=config.get('max_intensity', 1.0)
        )
    
    return palettes

def plot_color_grid(palettes=None):
    """
    Plot a grid of colored squares with different color schemes.
    
    Parameters:
    -----------
    palettes : dict or None
        Dictionary of color palettes for each quadrant. If None, uses default palettes.
    grid_size : tuple
        Size of the grid (rows, columns)
        
    Returns:
    --------
    Figure and axis objects
    """
    # Get color palettes
    if palettes is None:
        palettes = get_palette_set()
    grid_size=(8, 8)
    # Create a figure
    fig, ax = plt.subplots(figsize=(10, 10), frameon=False)
    
    # Calculate number of quadrants
    quad_rows = grid_size[0] // 4
    quad_cols = grid_size[1] // 4
    
    # Create the values matrix for each quadrant (values from 16 down to 1)
    values = np.arange(16, 0, -1).reshape(4, 4)
    
    # Map quadrant positions to palette keys
    position_mapping = {
        (0, 0): 'top_left',
        (0, 1): 'top_right',
        (1, 0): 'bottom_left',
        (1, 1): 'bottom_right'
    }
    
    # Plot each cell
    for quad_row in range(quad_rows):
        for quad_col in range(quad_cols):
            # Get the palette for this quadrant
            position = (quad_row, quad_col)
            palette_key = position_mapping.get(position, 'top_left')
            color_palette = list(reversed(palettes[palette_key]))
            
            for local_row in range(4):
                for local_col in range(4):
                    # Calculate global row and column
                    row = quad_row * 4 + local_row
                    col = quad_col * 4 + local_col
                    
                    # Get the value for this position
                    value = values[local_row, local_col]
                    
                    # Get color based on value (subtract 1 for 0-indexing)
                    color = color_palette[value - 1]
                    
                    # print(color)
                    # Plot the colored square
                    rect = plt.Rectangle((col, grid_size[0]-1-row), 1, 1, 
                                         facecolor=color, edgecolor='gray')
                    ax.add_patch(rect)
    
    # Set the axis limits and remove ticks
    ax.set_xlim(0, grid_size[1])
    ax.set_ylim(0, grid_size[0])
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect('equal')
    ax.axis('off')
    for a in [0,4,8]:
        ax.axhline(y=a, color='black', linestyle='-', linewidth=5)
        ax.axvline(x=a, color='black', linestyle='-', linewidth=5)

    _ = [s.set_visible(False) for s in ax.spines.values()]
    ax.set_frame_on(False)
    # # Add grid lines
    # for i in range(grid_size[0] + 1):
    #     ax.axhline(y=i, color='white', linewidth=1)
    # for j in range(grid_size[1] + 1):
    #     ax.axvline(x=j, color='white', linewidth=1)
    
    plt.tight_layout()
    return fig, ax

def plot_color_grid2(palettes=None):
    """
    Plot a grid of colored squares with different color schemes.
    
    Parameters:
    -----------
    palettes : dict or None
        Dictionary of color palettes for each quadrant. If None, uses default palettes.
    Returns:
    --------
    Figure and axis objects
    """
    # Get color palettes
    if palettes is None:
        palettes = get_palette_set()
    grid_size=(32, 64)
    # Create a figure
    fig, ax = plt.subplots(figsize=(10, 20), frameon=False)
    
    # Calculate number of quadrants
    # quad_rows = grid_size[0] // 2
    quad_rows = 2
    quad_cols = 16

    # assert it is perfectly divisible
    quad_size_rows = grid_size[0] // quad_rows
    quad_size_cols = grid_size[1] // quad_cols
    # quad_cols = grid_size[1] // 16
    
    # Create the values matrix for each quadrant (values from 16 down to 1)
    quad_size = quad_size_rows * quad_size_cols
    values = np.arange(quad_size, 0, -1).reshape((quad_size_rows, quad_size_cols), order='F')
    print(values)
    
    # Map quadrant positions to palette keys
    position_mapping = {
        (0, 0): 'top_left',
        (0, 1): 'top_right',
        (1, 0): 'bottom_left',
        (1, 1): 'bottom_right'
    }
    
    # Plot each cell
    for quad_row in range(quad_rows):
        for quad_col in range(quad_cols):
            # Get the palette for this quadrant
            position = (quad_row, quad_col)
            palette_key = position_mapping.get(position, 'top_left')
            color_palette = list(reversed(palettes[palette_key]))
            for local_col in range(quad_size_cols):
                for local_row in range(quad_size_rows):
                    # Calculate global row and column
                    row = quad_row * quad_size_rows + local_row
                    col = quad_col * quad_size_cols + local_col
                    
                    # Get the value for this position
                    value = values[local_row, local_col]
                    
                    color_gray_val = 1 - (value / quad_size)
                    color = tuple(np.repeat(color_gray_val, 3)) + (1.,)
                    
                    # print(color)
                    # Plot the colored square
                    rect = plt.Rectangle((col, grid_size[0]-1-row), 1, 1, 
                                         facecolor=color, edgecolor=color)
                    ax.add_patch(rect)
    
    # Set the axis limits and remove ticks
    ax.set_xlim(0, grid_size[1])
    ax.set_ylim(0, grid_size[0])
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect('equal')
    ax.axis('off')
    # for a in [0,4,8]:
    #     ax.axhline(y=a, color='black', linestyle='-', linewidth=5)
    #     ax.axvline(x=a, color='black', linestyle='-', linewidth=5)

    _ = [s.set_visible(False) for s in ax.spines.values()]
    ax.set_frame_on(False)
    # # Add grid lines
    # for i in range(grid_size[0] + 1):
    #     ax.axhline(y=i, color='white', linewidth=1)
    # for j in range(grid_size[1] + 1):
    #     ax.axvline(x=j, color='white', linewidth=1)
    
    plt.tight_layout()
    return fig, ax

def plot_color_grid3(palettes=None):
    """
    Plot a grid of colored squares with different color schemes.
    
    Parameters:
    -----------
    palettes : dict or None
        Dictionary of color palettes for each quadrant. If None, uses default palettes.
    Returns:
    --------
    Figure and axis objects
    """
    # Get color palettes
    if palettes is None:
        palettes = get_palette_set()
    grid_size=(32, 64)
    # Create a figure
    fig, ax = plt.subplots(figsize=(10, 20), frameon=False)
    
    # Calculate number of quadrants
    # quad_rows = grid_size[0] // 2
    quad_rows = 2
    quad_cols = 16

    # assert it is perfectly divisible
    quad_size_rows = grid_size[0] // quad_rows
    quad_size_cols = grid_size[1] // quad_cols
    # quad_cols = grid_size[1] // 16
    
    # Create the values matrix for each quadrant (values from 16 down to 1)
    quad_size = quad_size_rows * quad_size_cols
    values = np.arange(grid_size[0] * grid_size[1], 0, -1).reshape((quad_rows, quad_cols, quad_size_rows, quad_size_cols), order='C')
    print(values)
    max_val = grid_size[0] * grid_size[1]
    # Map quadrant positions to palette keys
    
    # Plot each cell
    for quad_row in range(quad_rows):
        for quad_col in range(quad_cols):
            # Get the palette for this quadrant
            for local_col in range(quad_size_cols):
                for local_row in range(quad_size_rows):
                    # Calculate global row and column
                    row = quad_row * quad_size_rows + local_row
                    col = quad_col * quad_size_cols + local_col
                    
                    # Get the value for this position
                    value = values[quad_row, quad_col, local_row, local_col]
                    
                    color_gray_val = 1 - (value / max_val)
                    color = tuple(np.repeat(color_gray_val, 3)) + (1.,)
                    
                    # print(color)
                    # Plot the colored square
                    rect = plt.Rectangle((col, grid_size[0]-1-row), 1, 1, 
                                         facecolor=color, edgecolor=color)
                    ax.add_patch(rect)
    
    # Set the axis limits and remove ticks
    ax.set_xlim(0, grid_size[1])
    ax.set_ylim(0, grid_size[0])
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect('equal')
    ax.axis('off')
    # for a in [0,4,8]:
    #     ax.axhline(y=a, color='black', linestyle='-', linewidth=5)
    #     ax.axvline(x=a, color='black', linestyle='-', linewidth=5)

    _ = [s.set_visible(False) for s in ax.spines.values()]
    ax.set_frame_on(False)
    # # Add grid lines
    # for i in range(grid_size[0] + 1):
    #     ax.axhline(y=i, color='white', linewidth=1)
    # for j in range(grid_size[1] + 1):
    #     ax.axvline(x=j, color='white', linewidth=1)
    
    plt.tight_layout()
    return fig, ax

def plot_color_line(palettes=None, grid_size=(8, 8)):
    """
    Plot a grid of colored squares with different color schemes.
    
    Parameters:
    -----------
    palettes : dict or None
        Dictionary of color palettes for each quadrant. If None, uses default palettes.
    grid_size : tuple
        Size of the grid (rows, columns)
        
    Returns:
    --------
    Figure and axis objects
    """
    fig, ax = plt.subplots(figsize=(12, 3), frameon=False)
    # Get color palettes
    if palettes is None:
        palettes = get_palette_set()
    
    # Flatten all palettes into a single list
    all_colors = []
    for key in ['top_left', 'top_right', 'bottom_left', 'bottom_right']:
        all_colors.extend(palettes[key])
    
    # Plot each cell in a linear arrangement
    num_cells = len(all_colors)
    for i, color in enumerate(all_colors):
        rect = plt.Rectangle((i, 0), 1, 5, linewidth=1, facecolor=color, edgecolor=color)
        ax.add_patch(rect)
    
    # Set axis limits and remove ticks
    ax.set_xlim(0, num_cells)
    ax.set_ylim(0, 5)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect('equal')
    ax.axis('off')
    for a in [0,16,32,48,64]:
        # ax.axhline(y=a, color='black', linestyle='-', linewidth=5)
        ax.axvline(x=a, color='black', linestyle='-', linewidth=5)
    ax.axhline(y=0, color='black', linestyle='-', linewidth=5)
    ax.axhline(y=5, color='black', linestyle='-', linewidth=5)

    _ = [s.set_visible(False) for s in ax.spines.values()]
    ax.set_frame_on(False)
    plt.tight_layout()
    return fig, ax

def create_quadrant_grid(figsize=(10, 10), grid_size=4, colormaps=None):
    """
    Create a 2x2 grid of colored quadrants, each with a grid_size x grid_size grid.
    
    Parameters:
    -----------
    figsize : tuple
        Figure size (width, height) in inches.
    grid_size : int
        Size of each quadrant grid (grid_size x grid_size).
    colormaps : list or None
        List of 4 colormap functions, one for each quadrant.
        If None, default colormaps will be used.
    
    Returns:
    --------
    fig, ax : matplotlib figure and axes
    """
    # Get colormaps if not provided
    if colormaps is None:
        colormaps = list(get_palette_set().values())
    
    # Create figure and axis
    fig, ax = plt.subplots(figsize=figsize)
    
    # Turn off axis
    ax.axis('off')
    
    # Total grid size
    total_size = grid_size * 2
    
    # Create a matrix of values for each quadrant
    values = np.zeros((total_size, total_size))
    
    # For each quadrant, populate values from grid_size*grid_size to 1 (e.g., 16 to 1)
    # going left to right, top to bottom
    for quadrant_row in range(2):
        for quadrant_col in range(2):
            for i in range(grid_size):
                for j in range(grid_size):
                    # Calculate the position within this quadrant
                    global_row = quadrant_row * grid_size + i
                    global_col = quadrant_col * grid_size + j
                    
                    # Calculate the value (e.g., 16 to 1, decreasing)
                    value = grid_size * grid_size - (i * grid_size + j)
                    
                    # Assign to the global matrix
                    values[global_row, global_col] = value
    
    # Create the grid of colored cells
    for i in range(total_size):
        for j in range(total_size):
            # Determine which quadrant this cell belongs to
            quadrant_row = i // grid_size
            quadrant_col = j // grid_size
            quadrant_idx = quadrant_row * 2 + quadrant_col
            
            # Get the colormap for this quadrant
            cmap = colormaps[quadrant_idx]
            
            # Get the normalized value for this cell (for color intensity)
            value = values[i, j]
            norm_value = (value - 1) / (grid_size * grid_size - 1)  # Normalized between 0 and 1
            
            # Get color from colormap
            color = cmap[i * grid_size + j]
            
            # Create rectangle for the cell
            rect = plt.Rectangle((j, total_size - i - 1), 1, 1, 
                               facecolor=color, edgecolor='white', linewidth=0.5)
            ax.add_patch(rect)
    
    # Set limits for the axis
    ax.set_xlim(0, total_size)
    ax.set_ylim(0, total_size)
    
    # Add grid lines
    for i in range(total_size + 1):
        ax.axhline(y=i, color='gray', linestyle='-', linewidth=0.5)
        ax.axvline(x=i, color='gray', linestyle='-', linewidth=0.5)
    
    # Add thicker lines to separate quadrants
    ax.axhline(y=grid_size, color='black', linestyle='-', linewidth=1.5)
    ax.axvline(x=grid_size, color='black', linestyle='-', linewidth=1.5)
    
    # Set aspect ratio to equal
    ax.set_aspect('equal')
    
    return fig, ax
# Example usage:
fig, ax = plot_color_grid()
# fig, ax = create_quadrant_grid()
plt.savefig("grid.svg")
# plt.show()
plt.close()
fig, ax = plot_color_line()
plt.savefig("line.svg")
plt.close()
fig, ax = plot_color_grid3()
plt.savefig("grid3.svg")
# Custom palette example:
"""
custom_palettes = get_palette_set({
    'top_left': {'color': 'green', 'min_intensity': 0.3, 'max_intensity': 0.9},
    'top_right': {'color': 'red', 'min_intensity': 0.3, 'max_intensity': 0.9},
    'bottom_left': {'color': 'blue', 'min_intensity': 0.3, 'max_intensity': 0.9},
    'bottom_right': {'color': 'yellow', 'min_intensity': 0.3, 'max_intensity': 0.9}
})
fig, ax = plot_color_grid(palettes=custom_palettes)
plt.show()
"""
