from __future__ import annotations
from ui_migration.arkui.formatting import page_number
from ui_migration.arkui.corners import CornerEmitter
from ui_migration.common import arkts_string


class SurfaceEmitter:
    def __init__(self, unresolved, tokens=None):
        self.unresolved = unresolved
        self.builders = []
        self.corners = CornerEmitter()
        from .style_tokens import StyleTokenEmitter
        self.tokens = tokens or StyleTokenEmitter()

    def emit(self, component, prefix):
        style = component['style']
        lines, size_updates, emitted_phase_paths = [], [], set()
        surface = style["surface"]
        background = surface["background"]
        token_background = self.tokens.expression(component, 'surface.background')
        if token_background:
            lines.append(f'{prefix}  .backgroundColor({token_background})')
            emitted_phase_paths.add('style.surface.background')
        elif isinstance(background, dict) and background.get("type") == "solid":
            lines.append(f"{prefix}  .backgroundColor({arkts_string(background['color'])})")
            emitted_phase_paths.add("style.surface.background")
        elif isinstance(background, dict) and background.get('type') == 'linear_gradient':
            direction = {0: 'Top', 90: 'Right', 180: 'Bottom', 270: 'Left'}.get(background.get('angle_degrees'))
            if background.get('direction') == 'right_bottom':
                direction = 'RightBottom'
            if direction and background.get('tile_mode', 'clamp') == 'clamp' and not any(
                key in background for key in ('center', 'radius_dp', 'resource')
            ):
                colors = background['colors']
                stops = background.get('stops') or [i / (len(colors) - 1) for i in range(len(colors))]
                pairs = ', '.join(f"[{arkts_string(color)}, {page_number(stop)}]" for color, stop in zip(colors, stops))
                lines.append(f"{prefix}  .linearGradient({{ direction: GradientDirection.{direction}, colors: [{pairs}], repeating: false }})")
                emitted_phase_paths.add('style.surface.background')
            else:
                self.unresolved(component, 'style.surface.background', 'gradient needs supported bounds-relative direction and clamp tile mode')
        if surface.get("alpha") is not None:
            lines.append(f"{prefix}  .opacity({page_number(surface['alpha'])})")
            emitted_phase_paths.add("style.surface.alpha")
        border = surface["border"]
        if isinstance(border, dict) and (
            border.get('edges') or border.get('dash_dp')
            or border.get('width_dp') is None or border.get('color') is None
        ):
            self.unresolved(component, 'style.surface.border', 'per-edge/custom-dash or incomplete border needs a dedicated draw renderer')
            border = None
        if isinstance(border, dict):
            border_parts = [
                f"width: Math.max(1, Math.ceil(this.getUIContext().vp2px({page_number(border['width_dp'])}))) + 'px'",
                f"color: {arkts_string(border['color'])}",
            ]
            if border.get("style") == "dashed":
                border_parts.append("style: BorderStyle.Dashed")
            elif border.get("style") == "dotted":
                border_parts.append("style: BorderStyle.Dotted")
            elif border.get("style") == "none":
                border_parts = ["width: 0"]
            emitted_phase_paths.add("style.surface.border")
        radius = surface["corner_radius_dp"]
        sizes = surface.get('corner_sizes')
        radius_expression = '0'
        token_radius = self.tokens.expression(component, 'surface.corner_radius_dp')
        if token_radius:
            radius_expression = token_radius
            emitted_phase_paths.add('style.surface.corner_radius_dp')
            if sizes is not None:
                emitted_phase_paths.add('style.surface.corner_sizes')
        elif isinstance(sizes, dict):
            radius_expression, updates = self.corners.emit(sizes)
            self.builders.append(self.corners.declarations[-1])
            size_updates.extend(updates)
            emitted_phase_paths.add('style.surface.corner_sizes')
            if radius is not None:
                emitted_phase_paths.add('style.surface.corner_radius_dp')
        elif isinstance(radius, dict):
            values = {name: page_number(radius[name]) for name in radius}
            if len(set(values.values())) == 1:
                radius_expression = values["top_left"]
            else:
                radius_expression = (
                    "{ topLeft: " + values["top_left"]
                    + ", topRight: " + values["top_right"]
                    + ", bottomRight: " + values["bottom_right"]
                    + ", bottomLeft: " + values["bottom_left"] + " }"
                )
            emitted_phase_paths.add("style.surface.corner_radius_dp")
        if token_radius or isinstance(sizes, dict) or isinstance(radius, dict):
            lines.append(f"{prefix}  .borderRadius({radius_expression})")
        if isinstance(border, dict):
            builder = f"pageBorder{len(self.builders)}"
            self.builders.append([
                f"  @State private {builder}Width: Length = 0",
                f"  @State private {builder}Height: Length = 0", "",
                "  @Builder", f"  private {builder}() {{", "    Stack() {}",
                f"      .width(this.{builder}Width)", f"      .height(this.{builder}Height)",
                f"      .border({{ {', '.join(border_parts)} }})",
                f"      .borderRadius({radius_expression})",
                "      .hitTestBehavior(HitTestMode.Transparent)", "  }", "",
            ])
            size_updates.extend([f'this.{builder}Width = current.width ?? 0', f'this.{builder}Height = current.height ?? 0'])
            lines.append(f"{prefix}  .overlay(this.{builder}(), {{ align: Alignment.Center }})")
        if surface.get("clip") is True:
            lines.append(f"{prefix}  .clip(true)")
            emitted_phase_paths.add("style.surface.clip")
        shadows = surface["shadows"]
        if isinstance(shadows, list) and (len(shadows) > 1 or any(shadow.get('spread_radius_dp') != 0 for shadow in shadows)):
            self.unresolved(component, 'style.surface.shadows', 'multiple shadows or spread cannot be represented by one ArkUI shadow')
            shadows = None
        if isinstance(shadows, list) and shadows:
            shadow = shadows[0]
            # ShadowOptions uses physical pixels, unlike most ArkUI dimensions.
            lines.append(
                f"{prefix}  .shadow({{ radius: this.getUIContext().vp2px({page_number(shadow['blur_radius_dp'])}), "
                f"color: {arkts_string(shadow['color'])}, "
                f"offsetX: this.getUIContext().vp2px({page_number(shadow['offset_x_dp'])}), "
                f"offsetY: this.getUIContext().vp2px({page_number(shadow['offset_y_dp'])}) }})"
            )
            emitted_phase_paths.add("style.surface.shadows")

        return lines, emitted_phase_paths, size_updates
