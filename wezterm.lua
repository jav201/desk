-- desk :: frameless desktop-widget WezTerm config
--
-- WezTerm can remove the window chrome that Windows Terminal / PowerShell cannot.
-- Install WezTerm: https://wezterm.org
--
-- Use: copy this to  ~/.wezterm.lua  (C:\Users\<you>\.wezterm.lua), then run `desk`.
-- Pin it always-on-top with PowerToys -> Always On Top (Win+Ctrl+T).

local wezterm = require 'wezterm'
local config = wezterm.config_builder()

config.window_decorations = 'NONE'          -- frameless
config.enable_tab_bar = false
config.hide_tab_bar_if_only_one_tab = true
config.window_background_opacity = 0.92
config.initial_cols = 84
config.initial_rows = 26
config.window_padding = { left = 6, right = 6, top = 4, bottom = 4 }
config.color_scheme = nil
config.colors = { background = '#0d1117', foreground = '#c9d4e0' }

-- Opens your normal shell (frameless) so you can run `desk` (or any widget).
-- For a dedicated always-desk window, uncomment:
--   config.default_prog = { 'desk' }

config.keys = {
  -- Ctrl+Shift+B : toggle the frame on/off (NONE <-> TITLE|RESIZE)
  {
    key = 'b', mods = 'CTRL|SHIFT',
    action = wezterm.action_callback(function(window, _pane)
      local o = window:get_config_overrides() or {}
      if o.window_decorations == 'TITLE | RESIZE' then
        o.window_decorations = 'NONE'
      else
        o.window_decorations = 'TITLE | RESIZE'
      end
      window:set_config_overrides(o)
    end),
  },
  { key = 'F11', action = wezterm.action.ToggleFullScreen },
  { key = 'v', mods = 'CTRL',       action = wezterm.action.PasteFrom 'Clipboard' },
  { key = 'v', mods = 'CTRL|SHIFT', action = wezterm.action.PasteFrom 'Clipboard' },
  { key = 'c', mods = 'CTRL|SHIFT', action = wezterm.action.CopyTo 'Clipboard' },
}

return config
