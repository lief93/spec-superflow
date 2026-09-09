from .dialog import Dialog
from .alert_dialog import AlertDialog
from .modal_bottom_sheet import ModalBottomSheet
from .dropdown_menu import DropdownMenu
from .dropdown_menu_item import DropdownMenuItem
from .exposed_dropdown_menu_box import ExposedDropdownMenuBox
from .tab import Tab
from .tab_row import TabRow
from .primary_tab_row import PrimaryTabRow
from .secondary_tab_row import SecondaryTabRow
from .navigation_bar import NavigationBar
from .navigation_bar_item import NavigationBarItem
from .navigation_drawer import NavigationDrawer
from .navigation_rail import NavigationRail
from .navigation_rail_item import NavigationRailItem
from .flow_row import FlowRow
from .contextual_flow_row import ContextualFlowRow
from .lazy_vertical_grid import LazyVerticalGrid
from .lazy_vertical_staggered_grid import LazyVerticalStaggeredGrid


class ControlRegistry:
    def __init__(self, controls):
        self._controls = {}
        for control in controls:
            if control.name in self._controls:
                raise ValueError('duplicate control: ' + control.name)
            self._controls[control.name] = control

    def get(self, name):
        return self._controls.get(name)

    def __iter__(self):
        return iter(self._controls.values())

    @property
    def names(self):
        return frozenset(self._controls)


CONTROLS = ControlRegistry((Dialog(), AlertDialog(), ModalBottomSheet(), DropdownMenu(),
    DropdownMenuItem(), ExposedDropdownMenuBox(), Tab(), TabRow(), PrimaryTabRow(), SecondaryTabRow(),
    NavigationBar(), NavigationBarItem(), NavigationDrawer(), NavigationRail(), NavigationRailItem(),
    FlowRow(), ContextualFlowRow(), LazyVerticalGrid(), LazyVerticalStaggeredGrid()))
