"""A static force plot and optional overlays on the images the model actually saw."""


from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PIL import Image

from .anatomy import LANDMARKS
from .mechanics import FIELDS


def draw_report(result, observation, views, folder):
    samples = result["samples"]
    scaled = result["plate_kg"] is not None
    field = "force_kgf" if scaled else "newtons_per_kg"
    fig = Figure(figsize=(7, 4), layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    discrete = result["mechanism"] == "belt_cam"
    ax.plot([s["travel_pct"] for s in samples], [s[field] for s in samples],
            color="#14766a", linestyle="none" if discrete else "-", marker="o" if discrete else None)
    ax.set(xlim=(-3, 103), xlabel="Travel from first to last pose (%)",
           ylabel="Contact force (kgf)" if scaled else "Contact force per kg of plates (N/kg)",
           title="Resistance from added plates")
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", alpha=.25)
    fig.savefig(folder / "profile.png", dpi=150)
    for i, (pose, path) in enumerate(zip(observation["poses"], views), 1):
        fig = Figure(figsize=(6, 6), layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        with Image.open(path) as photo:
            ax.imshow(photo)
        for field in (*FIELDS[result["mechanism"]], *(k for k in LANDMARKS if k in pose)):
            x, y = pose[field]
            ax.scatter(x, y, color="#e13b48", s=24)
            ax.annotate(field, (x, y), xytext=(3, 5), textcoords="offset points",
                        bbox={"facecolor": "white", "alpha": .8, "edgecolor": "none"})
        if result["mechanism"] == "belt_cam":
            ax.plot(*zip(pose["belt_load"], pose["belt_cam"]), color="#e13b48")
        ax.set(xlim=(0, 1000), ylim=(1000, 0))
        ax.axis("off")
        fig.savefig(folder / f"landmarks-{i:03}.png", dpi=125)
