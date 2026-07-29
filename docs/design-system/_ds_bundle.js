/* @ds-bundle: {"format":4,"namespace":"DISPDesignSystem_bf3b97","components":[{"name":"Avatar","sourcePath":"components/core/Avatar.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Icon","sourcePath":"components/core/Icon.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"Tag","sourcePath":"components/core/Tag.jsx"},{"name":"TileItem","sourcePath":"components/data/TileCard.jsx"},{"name":"TileCard","sourcePath":"components/data/TileCard.jsx"},{"name":"EmptyState","sourcePath":"components/feedback/EmptyState.jsx"},{"name":"ErrorView","sourcePath":"components/feedback/ErrorView.jsx"},{"name":"OfflineBanner","sourcePath":"components/feedback/OfflineBanner.jsx"},{"name":"SkeletonBlock","sourcePath":"components/feedback/SkeletonBlock.jsx"},{"name":"Toast","sourcePath":"components/feedback/Toast.jsx"},{"name":"SecretField","sourcePath":"components/forms/SecretField.jsx"},{"name":"SelectField","sourcePath":"components/forms/SelectField.jsx"},{"name":"Switch","sourcePath":"components/forms/Switch.jsx"},{"name":"TextField","sourcePath":"components/forms/TextField.jsx"},{"name":"BottomNav","sourcePath":"components/navigation/BottomNav.jsx"},{"name":"SideNav","sourcePath":"components/navigation/SideNav.jsx"},{"name":"Tabs","sourcePath":"components/navigation/Tabs.jsx"},{"name":"TopBar","sourcePath":"components/navigation/TopBar.jsx"},{"name":"Dialog","sourcePath":"components/overlay/Dialog.jsx"},{"name":"Menu","sourcePath":"components/overlay/Menu.jsx"},{"name":"Tooltip","sourcePath":"components/overlay/Tooltip.jsx"}],"sourceHashes":{"components/core/Avatar.jsx":"152e1951340f","components/core/Badge.jsx":"22d273d256c3","components/core/Button.jsx":"8da5a7dd168d","components/core/Icon.jsx":"8bb7d22501db","components/core/IconButton.jsx":"696c7621dc1c","components/core/Tag.jsx":"ed6ae5947887","components/data/TileCard.jsx":"7d311ac1f6f4","components/feedback/EmptyState.jsx":"5566a2418a04","components/feedback/ErrorView.jsx":"f6cb79e0b4d8","components/feedback/OfflineBanner.jsx":"b0d2ea3480f9","components/feedback/SkeletonBlock.jsx":"f58c5aba5435","components/feedback/Toast.jsx":"8babcd15a17c","components/forms/SecretField.jsx":"9e156dd7810d","components/forms/SelectField.jsx":"526c4eec6c1c","components/forms/Switch.jsx":"c1f4687e1c44","components/forms/TextField.jsx":"05984bfb3d11","components/navigation/BottomNav.jsx":"b8cc2edfa371","components/navigation/SideNav.jsx":"92030685f845","components/navigation/Tabs.jsx":"f38a3220c1fa","components/navigation/TopBar.jsx":"518199764549","components/overlay/Dialog.jsx":"d3cbcf34596a","components/overlay/Menu.jsx":"6289d0b62be4","components/overlay/Tooltip.jsx":"55e040cd0c4d","ui_kits/disp-client/App.jsx":"69490ab1aed1","ui_kits/disp-client/screens/AccountScreen.jsx":"bc0ef4bed744","ui_kits/disp-client/screens/DashboardScreen.jsx":"c321402b7ba6","ui_kits/disp-client/screens/LoginScreen.jsx":"a09914488728","ui_kits/disp-client/screens/NotesScreen.jsx":"0292405d46c0"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.DISPDesignSystem_bf3b97 = window.DISPDesignSystem_bf3b97 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Avatar.jsx
try { (() => {
function Avatar({
  name,
  size = 32
}) {
  const initials = name.trim().split(/\s+/).slice(0, 2).map(w => w[0]?.toUpperCase()).join("");
  return /*#__PURE__*/React.createElement("span", {
    style: {
      width: size,
      height: size,
      borderRadius: "var(--radius-full)",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      background: "var(--color-accent)",
      color: "var(--color-accent-text)",
      fontSize: size * 0.4,
      fontWeight: "var(--font-weight-semibold)",
      flex: "0 0 auto"
    }
  }, initials || "?");
}
Object.assign(__ds_scope, { Avatar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Avatar.jsx", error: String((e && e.message) || e) }); }

// components/core/Badge.jsx
try { (() => {
function Badge({
  children,
  tone = "neutral"
}) {
  const tones = {
    neutral: {
      background: "var(--color-surface-sunken)",
      color: "var(--color-text-muted)",
      border: "var(--color-border)"
    },
    success: {
      background: "color-mix(in oklch, var(--color-success) 16%, var(--color-surface-raised))",
      color: "var(--color-success)",
      border: "transparent"
    },
    warning: {
      background: "color-mix(in oklch, var(--color-warning) 16%, var(--color-surface-raised))",
      color: "var(--color-warning)",
      border: "transparent"
    },
    danger: {
      background: "color-mix(in oklch, var(--color-danger) 16%, var(--color-surface-raised))",
      color: "var(--color-danger)",
      border: "transparent"
    },
    accent: {
      background: "color-mix(in oklch, var(--color-accent) 16%, var(--color-surface-raised))",
      color: "var(--color-accent)",
      border: "transparent"
    }
  };
  const t = tones[tone];
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      padding: "2px 8px",
      fontSize: "var(--text-xs)",
      fontWeight: "var(--font-weight-medium)",
      borderRadius: "var(--radius-full)",
      background: t.background,
      color: t.color,
      border: `1px solid ${t.border}`,
      lineHeight: 1.4
    }
  }, children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function Button({
  children,
  variant = "primary",
  size = "md",
  disabled,
  onClick,
  type = "button"
}) {
  const base = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    fontFamily: "var(--font-sans)",
    fontWeight: "var(--font-weight-medium)",
    borderRadius: "var(--radius-sm)",
    cursor: disabled ? "default" : "pointer",
    transition: "background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard), opacity var(--duration-fast) var(--ease-standard)",
    opacity: disabled ? 0.5 : 1,
    border: "1px solid transparent",
    fontSize: size === "sm" ? "var(--text-sm)" : "var(--text-base)",
    padding: size === "sm" ? "6px 12px" : "10px 16px",
    minHeight: size === "sm" ? 32 : 44
  };
  const variants = {
    primary: {
      background: "var(--color-accent)",
      color: "var(--color-accent-text)"
    },
    secondary: {
      background: "var(--color-surface-raised)",
      color: "var(--color-text)",
      borderColor: "var(--color-border)"
    },
    ghost: {
      background: "transparent",
      color: "var(--color-text)"
    },
    danger: {
      background: "var(--color-danger)",
      color: "var(--color-accent-text)"
    }
  };
  return /*#__PURE__*/React.createElement("button", {
    type: type,
    disabled: disabled,
    onClick: onClick,
    style: {
      ...base,
      ...variants[variant]
    }
  }, children);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Icon.jsx
try { (() => {
function Icon({
  name,
  size = 20
}) {
  const url = `https://unpkg.com/lucide-static@0.462.0/icons/${name}.svg`;
  return /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      display: "inline-block",
      flex: "0 0 auto",
      width: size,
      height: size,
      backgroundColor: "currentColor",
      WebkitMaskImage: `url(${url})`,
      maskImage: `url(${url})`,
      WebkitMaskSize: "contain",
      maskSize: "contain",
      WebkitMaskRepeat: "no-repeat",
      maskRepeat: "no-repeat",
      WebkitMaskPosition: "center",
      maskPosition: "center"
    }
  });
}
Object.assign(__ds_scope, { Icon });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Icon.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function IconButton({
  children,
  label,
  variant = "ghost",
  size = "md",
  onClick
}) {
  const dim = size === "sm" ? 32 : 44;
  return /*#__PURE__*/React.createElement("button", {
    "aria-label": label,
    title: label,
    onClick: onClick,
    style: {
      width: dim,
      height: dim,
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      borderRadius: "var(--radius-sm)",
      cursor: "pointer",
      background: variant === "secondary" ? "var(--color-surface-raised)" : "transparent",
      border: variant === "secondary" ? "1px solid var(--color-border)" : "1px solid transparent",
      color: "var(--color-text)",
      transition: "background var(--duration-fast) var(--ease-standard)"
    }
  }, children);
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/core/Tag.jsx
try { (() => {
function Tag({
  children,
  onRemove
}) {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      padding: "4px 8px 4px 10px",
      fontSize: "var(--text-sm)",
      borderRadius: "var(--radius-sm)",
      background: "var(--color-surface-sunken)",
      color: "var(--color-text)",
      border: "1px solid var(--color-border)"
    }
  }, children, onRemove && /*#__PURE__*/React.createElement("button", {
    onClick: onRemove,
    "aria-label": `Remove ${children}`,
    style: {
      display: "inline-flex",
      border: "none",
      background: "transparent",
      cursor: "pointer",
      color: "var(--color-text-muted)",
      padding: 0
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "x",
    size: 14
  })));
}
Object.assign(__ds_scope, { Tag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Tag.jsx", error: String((e && e.message) || e) }); }

// components/data/TileCard.jsx
try { (() => {
function TileItem({
  primary,
  secondary,
  badge
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 8,
      padding: "8px 0"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      color: "var(--color-text)",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, primary), secondary && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--color-text-muted)"
    }
  }, secondary)), badge);
}
function TileCard({
  title,
  icon,
  children,
  actions,
  onRefresh,
  state = "default"
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--color-surface-raised)",
      border: "1px solid var(--color-border)",
      borderRadius: "var(--radius-md)",
      padding: "var(--space-4)",
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: icon,
    size: 18
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: "var(--font-weight-medium)",
      fontSize: "var(--text-base)"
    }
  }, title)), onRefresh && /*#__PURE__*/React.createElement(__ds_scope.IconButton, {
    label: "Refresh",
    size: "sm",
    onClick: onRefresh
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "refresh-cw",
    size: 15
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      borderTop: "1px solid var(--color-border)",
      marginTop: 2
    }
  }, state === "loading" ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10,
      padding: "10px 0"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "block",
      height: 14,
      width: "70%",
      borderRadius: "var(--radius-sm)",
      background: "var(--color-surface-sunken)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "block",
      height: 14,
      width: "45%",
      borderRadius: "var(--radius-sm)",
      background: "var(--color-surface-sunken)"
    }
  })) : children), actions && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8,
      marginTop: 4
    }
  }, actions));
}
Object.assign(__ds_scope, { TileItem, TileCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/TileCard.jsx", error: String((e && e.message) || e) }); }

// components/feedback/EmptyState.jsx
try { (() => {
// Terse, factual copy — no illustration, no encouragement-flavored copy.
function EmptyState({
  icon = "inbox",
  title,
  description,
  action
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      textAlign: "center",
      gap: 8,
      padding: "var(--space-8) var(--space-4)",
      color: "var(--color-text-muted)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 40,
      height: 40,
      borderRadius: "var(--radius-md)",
      background: "var(--color-surface-sunken)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: icon,
    size: 20
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--color-text)",
      fontWeight: "var(--font-weight-medium)",
      fontSize: "var(--text-base)"
    }
  }, title), description && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      maxWidth: "32ch"
    }
  }, description), action && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 8
    }
  }, action));
}
Object.assign(__ds_scope, { EmptyState });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/EmptyState.jsx", error: String((e && e.message) || e) }); }

// components/feedback/ErrorView.jsx
try { (() => {
function ErrorView({
  title = "Something went wrong",
  message,
  onRetry,
  fullPage
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      textAlign: "center",
      gap: 8,
      padding: fullPage ? "var(--space-12) var(--space-4)" : "var(--space-6) var(--space-4)",
      justifyContent: fullPage ? "center" : undefined,
      minHeight: fullPage ? "60vh" : undefined
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 40,
      height: 40,
      borderRadius: "var(--radius-md)",
      background: "color-mix(in oklch, var(--color-danger) 14%, var(--color-surface-raised))",
      color: "var(--color-danger)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "triangle-alert",
    size: 20
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: "var(--font-weight-medium)",
      fontSize: "var(--text-base)"
    }
  }, title), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      color: "var(--color-text-muted)",
      maxWidth: "40ch"
    }
  }, message), onRetry && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 8
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Button, {
    size: "sm",
    variant: "secondary",
    onClick: onRetry
  }, "Try again")));
}
Object.assign(__ds_scope, { ErrorView });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/ErrorView.jsx", error: String((e && e.message) || e) }); }

// components/feedback/OfflineBanner.jsx
try { (() => {
function OfflineBanner({
  showingSavedData
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      padding: "8px 16px",
      background: "var(--color-surface-sunken)",
      color: "var(--color-text-muted)",
      borderBottom: "1px solid var(--color-border)",
      fontSize: "var(--text-sm)"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "wifi-off",
    size: 16
  }), /*#__PURE__*/React.createElement("span", null, "You're offline.", showingSavedData ? " Showing saved data." : ""));
}
Object.assign(__ds_scope, { OfflineBanner });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/OfflineBanner.jsx", error: String((e && e.message) || e) }); }

// components/feedback/SkeletonBlock.jsx
try { (() => {
// Static muted block — no shimmer animation per motion spec.
function SkeletonBlock({
  width = "100%",
  height = 16
}) {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: "block",
      width,
      height,
      borderRadius: "var(--radius-sm)",
      background: "var(--color-surface-sunken)"
    }
  });
}
Object.assign(__ds_scope, { SkeletonBlock });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/SkeletonBlock.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Toast.jsx
try { (() => {
function Toast({
  message,
  tone = "neutral",
  actionLabel,
  onAction,
  onDismiss
}) {
  const accent = tone === "success" ? "var(--color-success)" : tone === "danger" ? "var(--color-danger)" : "var(--color-text-muted)";
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 12,
      padding: "12px 14px",
      maxWidth: 380,
      background: "var(--color-surface-raised)",
      color: "var(--color-text)",
      borderRadius: "var(--radius-md)",
      boxShadow: "var(--shadow-overlay)",
      border: "1px solid var(--color-border)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 6,
      height: 6,
      borderRadius: "50%",
      background: accent,
      flex: "0 0 auto"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      fontSize: "var(--text-sm)"
    }
  }, message), actionLabel && /*#__PURE__*/React.createElement("button", {
    onClick: onAction,
    style: {
      background: "none",
      border: "none",
      color: "var(--color-accent)",
      fontWeight: "var(--font-weight-medium)",
      fontSize: "var(--text-sm)",
      cursor: "pointer"
    }
  }, actionLabel), onDismiss && /*#__PURE__*/React.createElement("button", {
    "aria-label": "Dismiss",
    onClick: onDismiss,
    style: {
      background: "none",
      border: "none",
      color: "var(--color-text-muted)",
      cursor: "pointer",
      display: "flex"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "x",
    size: 16
  })));
}
Object.assign(__ds_scope, { Toast });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Toast.jsx", error: String((e && e.message) || e) }); }

// components/forms/SecretField.jsx
try { (() => {
const {
  useState
} = React;
// Secret fields never echo the real plaintext back from the server — "reveal" only
// ever un-masks the masked placeholder (e.g. a suffix hint). Replacing requires a new value.
function SecretField({
  label,
  maskedValue,
  helpText,
  onReplace
}) {
  const [revealed, setRevealed] = useState(false);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 6,
      width: "100%"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      fontWeight: "var(--font-weight-medium)"
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-sm)",
      padding: "10px 12px",
      minHeight: 44,
      borderRadius: "var(--radius-sm)",
      border: "1px solid var(--color-border)",
      background: "var(--color-surface-sunken)",
      color: "var(--color-text)",
      display: "flex",
      alignItems: "center",
      letterSpacing: revealed ? "normal" : "0.08em"
    }
  }, revealed ? maskedValue : maskedValue.replace(/[^•]/g, m => m)), /*#__PURE__*/React.createElement("button", {
    "aria-label": revealed ? "Hide" : "Show",
    onClick: () => setRevealed(r => !r),
    style: {
      width: 44,
      height: 44,
      borderRadius: "var(--radius-sm)",
      border: "1px solid var(--color-border)",
      background: "var(--color-surface-raised)",
      color: "var(--color-text)",
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: revealed ? "eye-off" : "eye",
    size: 18
  })), onReplace && /*#__PURE__*/React.createElement(__ds_scope.Button, {
    variant: "secondary",
    size: "sm",
    onClick: onReplace
  }, "Replace")), helpText && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--color-text-muted)"
    }
  }, helpText));
}
Object.assign(__ds_scope, { SecretField });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/SecretField.jsx", error: String((e && e.message) || e) }); }

// components/forms/SelectField.jsx
try { (() => {
function SelectField({
  label,
  value,
  options,
  onChange,
  helpText
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 6,
      width: "100%"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      fontWeight: "var(--font-weight-medium)"
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      display: "block"
    }
  }, /*#__PURE__*/React.createElement("select", {
    value: value,
    onChange: e => onChange && onChange(e.target.value),
    style: {
      font: "inherit",
      fontSize: "var(--text-base)",
      padding: "10px 36px 10px 12px",
      minHeight: 44,
      width: "100%",
      borderRadius: "var(--radius-sm)",
      border: "1px solid var(--color-border)",
      background: "var(--color-surface-raised)",
      color: "var(--color-text)",
      appearance: "none",
      outline: "none"
    }
  }, options.map(o => /*#__PURE__*/React.createElement("option", {
    key: o.value,
    value: o.value
  }, o.label))), /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      right: 12,
      top: "50%",
      transform: "translateY(-50%)",
      color: "var(--color-text-muted)",
      pointerEvents: "none"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "chevron-down",
    size: 16
  }))), helpText && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--color-text-muted)"
    }
  }, helpText));
}
Object.assign(__ds_scope, { SelectField });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/SelectField.jsx", error: String((e && e.message) || e) }); }

// components/forms/Switch.jsx
try { (() => {
function Switch({
  checked,
  onChange,
  label,
  disabled
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 10,
      cursor: disabled ? "default" : "pointer",
      opacity: disabled ? 0.5 : 1
    }
  }, /*#__PURE__*/React.createElement("span", {
    onClick: () => !disabled && onChange(!checked),
    role: "switch",
    "aria-checked": checked,
    style: {
      width: 40,
      height: 24,
      borderRadius: "var(--radius-full)",
      position: "relative",
      flex: "0 0 auto",
      background: checked ? "var(--color-accent)" : "var(--color-surface-sunken)",
      border: "1px solid " + (checked ? "transparent" : "var(--color-border)"),
      transition: "background var(--duration-fast) var(--ease-standard)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      top: 2,
      left: checked ? 18 : 2,
      width: 18,
      height: 18,
      borderRadius: "50%",
      background: "var(--color-surface-raised)",
      transition: "left var(--duration-fast) var(--ease-standard)",
      boxShadow: "0 1px 2px rgba(0,0,0,0.2)"
    }
  })), label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-base)"
    }
  }, label));
}
Object.assign(__ds_scope, { Switch });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Switch.jsx", error: String((e && e.message) || e) }); }

// components/forms/TextField.jsx
try { (() => {
function TextField({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  helpText,
  error,
  disabled
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 6,
      width: "100%"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      fontWeight: "var(--font-weight-medium)"
    }
  }, label), /*#__PURE__*/React.createElement("input", {
    type: type,
    value: value,
    placeholder: placeholder,
    disabled: disabled,
    onChange: e => onChange && onChange(e.target.value),
    style: {
      font: "inherit",
      fontSize: "var(--text-base)",
      padding: "10px 12px",
      minHeight: 44,
      borderRadius: "var(--radius-sm)",
      border: `1px solid ${error ? "var(--color-danger)" : "var(--color-border)"}`,
      background: "var(--color-surface-raised)",
      color: "var(--color-text)",
      outline: "none",
      transition: "border-color var(--duration-fast) var(--ease-standard)"
    }
  }), error ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--color-danger)"
    }
  }, error) : helpText ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--color-text-muted)"
    }
  }, helpText) : null);
}
Object.assign(__ds_scope, { TextField });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/TextField.jsx", error: String((e && e.message) || e) }); }

// components/navigation/BottomNav.jsx
try { (() => {
// Mobile only (below md/768px). Sits below toasts in stacking order.
function BottomNav({
  links
}) {
  return /*#__PURE__*/React.createElement("nav", {
    style: {
      display: "flex",
      borderTop: "1px solid var(--color-border)",
      background: "var(--color-surface-raised)",
      position: "sticky",
      bottom: 0,
      zIndex: 30
    }
  }, links.map((l, i) => /*#__PURE__*/React.createElement("button", {
    key: i,
    onClick: l.onClick,
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      gap: 4,
      padding: "8px 4px 10px",
      minHeight: 56,
      border: "none",
      background: "transparent",
      cursor: "pointer",
      color: l.active ? "var(--color-accent)" : "var(--color-text-muted)"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: l.icon,
    size: 20
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)"
    }
  }, l.label))));
}
Object.assign(__ds_scope, { BottomNav });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/BottomNav.jsx", error: String((e && e.message) || e) }); }

// components/navigation/SideNav.jsx
try { (() => {
// Appears at md+ (768px); below that, use BottomNav instead.
function SideNav({
  links
}) {
  return /*#__PURE__*/React.createElement("nav", {
    style: {
      width: 220,
      flex: "0 0 auto",
      padding: "var(--space-4) var(--space-2)",
      borderRight: "1px solid var(--color-border)",
      display: "flex",
      flexDirection: "column",
      gap: 2
    }
  }, links.map((l, i) => /*#__PURE__*/React.createElement("button", {
    key: i,
    onClick: l.onClick,
    style: {
      display: "flex",
      alignItems: "center",
      gap: 10,
      padding: "8px 12px",
      borderRadius: "var(--radius-sm)",
      border: "none",
      cursor: "pointer",
      textAlign: "left",
      fontSize: "var(--text-sm)",
      background: l.active ? "var(--color-surface-sunken)" : "transparent",
      color: l.active ? "var(--color-text)" : "var(--color-text-muted)",
      fontWeight: l.active ? "var(--font-weight-medium)" : "var(--font-weight-regular)"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: l.icon,
    size: 18
  }), l.label)));
}
Object.assign(__ds_scope, { SideNav });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/SideNav.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Tabs.jsx
try { (() => {
function Tabs({
  tabs,
  active,
  onChange
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 4,
      borderBottom: "1px solid var(--color-border)"
    }
  }, tabs.map((t, i) => /*#__PURE__*/React.createElement("button", {
    key: i,
    onClick: () => onChange(i),
    style: {
      padding: "10px 4px",
      marginRight: 20,
      background: "none",
      border: "none",
      cursor: "pointer",
      fontSize: "var(--text-sm)",
      fontWeight: "var(--font-weight-medium)",
      color: active === i ? "var(--color-text)" : "var(--color-text-muted)",
      borderBottom: active === i ? "2px solid var(--color-accent)" : "2px solid transparent",
      marginBottom: -1,
      transition: "color var(--duration-fast) var(--ease-standard)"
    }
  }, t)));
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Tabs.jsx", error: String((e && e.message) || e) }); }

// components/navigation/TopBar.jsx
try { (() => {
function TopBar({
  userMenu,
  title = "DISP"
}) {
  return /*#__PURE__*/React.createElement("header", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      height: 56,
      padding: "0 var(--space-4)",
      borderBottom: "1px solid var(--color-border)",
      background: "var(--color-surface-raised)",
      position: "sticky",
      top: 0,
      zIndex: 30
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: "var(--font-weight-semibold)",
      fontSize: "var(--text-md)",
      letterSpacing: "var(--tracking-tight)"
    }
  }, title), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      display: "flex",
      alignItems: "center"
    }
  }, userMenu));
}
Object.assign(__ds_scope, { TopBar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/TopBar.jsx", error: String((e && e.message) || e) }); }

// components/overlay/Dialog.jsx
try { (() => {
function Dialog({
  open,
  title,
  children,
  onClose,
  footer
}) {
  if (!open) return null;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: 0,
      background: "rgba(13,15,18,0.4)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: 16,
      zIndex: 50,
      transition: "opacity var(--duration-overlay) var(--ease-standard)"
    },
    onClick: onClose
  }, /*#__PURE__*/React.createElement("div", {
    onClick: e => e.stopPropagation(),
    style: {
      width: "100%",
      maxWidth: 440,
      background: "var(--color-surface-raised)",
      color: "var(--color-text)",
      borderRadius: "var(--radius-lg)",
      boxShadow: "var(--shadow-overlay)",
      border: "1px solid var(--color-border)",
      display: "flex",
      flexDirection: "column",
      maxHeight: "85vh"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "16px 16px 12px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-lg)",
      fontWeight: "var(--font-weight-semibold)"
    }
  }, title), /*#__PURE__*/React.createElement(__ds_scope.IconButton, {
    label: "Close",
    onClick: onClose
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "x",
    size: 18
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "0 16px 16px",
      overflowY: "auto"
    }
  }, children), footer && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "flex-end",
      gap: 8,
      padding: "12px 16px",
      borderTop: "1px solid var(--color-border)"
    }
  }, footer)));
}
Object.assign(__ds_scope, { Dialog });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/overlay/Dialog.jsx", error: String((e && e.message) || e) }); }

// components/overlay/Menu.jsx
try { (() => {
function Menu({
  open,
  items,
  onClose,
  align = "right"
}) {
  if (!open) return null;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    onClick: onClose,
    style: {
      position: "fixed",
      inset: 0,
      zIndex: 40
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      top: "calc(100% + 6px)",
      [align]: 0,
      minWidth: 200,
      background: "var(--color-surface-raised)",
      border: "1px solid var(--color-border)",
      borderRadius: "var(--radius-md)",
      boxShadow: "var(--shadow-overlay)",
      padding: 6,
      zIndex: 50
    }
  }, items.map((item, i) => /*#__PURE__*/React.createElement("button", {
    key: i,
    onClick: () => {
      item.onClick && item.onClick();
      onClose();
    },
    style: {
      display: "flex",
      alignItems: "center",
      gap: 10,
      width: "100%",
      padding: "8px 10px",
      background: "transparent",
      border: "none",
      borderRadius: "var(--radius-sm)",
      cursor: "pointer",
      fontSize: "var(--text-sm)",
      color: item.danger ? "var(--color-danger)" : "var(--color-text)",
      textAlign: "left"
    }
  }, item.icon && /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: item.icon,
    size: 16
  }), item.label))));
}
Object.assign(__ds_scope, { Menu });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/overlay/Menu.jsx", error: String((e && e.message) || e) }); }

// components/overlay/Tooltip.jsx
try { (() => {
const {
  useState
} = React;
function Tooltip({
  label,
  children
}) {
  const [show, setShow] = useState(false);
  return /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      display: "inline-flex"
    },
    onMouseEnter: () => setShow(true),
    onMouseLeave: () => setShow(false),
    onFocus: () => setShow(true),
    onBlur: () => setShow(false)
  }, children, show && /*#__PURE__*/React.createElement("span", {
    role: "tooltip",
    style: {
      position: "absolute",
      bottom: "calc(100% + 6px)",
      left: "50%",
      transform: "translateX(-50%)",
      background: "var(--color-text)",
      color: "var(--color-surface)",
      fontSize: "var(--text-xs)",
      padding: "4px 8px",
      borderRadius: "var(--radius-sm)",
      whiteSpace: "nowrap",
      boxShadow: "var(--shadow-overlay)",
      zIndex: 60
    }
  }, label));
}
Object.assign(__ds_scope, { Tooltip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/overlay/Tooltip.jsx", error: String((e && e.message) || e) }); }

// ui_kits/disp-client/App.jsx
try { (() => {
function AppShell({
  screen,
  setScreen,
  children
}) {
  const {
    TopBar,
    SideNav,
    BottomNav,
    IconButton,
    Icon,
    Avatar,
    Menu,
    OfflineBanner
  } = window.DISPDesignSystem_bf3b97;
  const {
    useState
  } = React;
  const [menuOpen, setMenuOpen] = useState(false);
  const [offline, setOffline] = useState(false);
  const links = [{
    label: "Dashboard",
    icon: "layout-grid",
    active: screen === "dashboard",
    onClick: () => setScreen("dashboard")
  }, {
    label: "Notes",
    icon: "file-text",
    active: screen === "notes",
    onClick: () => setScreen("notes")
  }, {
    label: "Account",
    icon: "user",
    active: screen === "account",
    onClick: () => setScreen("account")
  }];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      height: "100%",
      display: "flex",
      flexDirection: "column"
    }
  }, offline && /*#__PURE__*/React.createElement(OfflineBanner, {
    showingSavedData: true
  }), /*#__PURE__*/React.createElement(TopBar, {
    userMenu: /*#__PURE__*/React.createElement("div", {
      style: {
        position: "relative"
      }
    }, /*#__PURE__*/React.createElement(IconButton, {
      label: "User menu",
      onClick: () => setMenuOpen(o => !o)
    }, /*#__PURE__*/React.createElement(Avatar, {
      name: "Jordan Lee",
      size: 28
    })), /*#__PURE__*/React.createElement(Menu, {
      open: menuOpen,
      onClose: () => setMenuOpen(false),
      items: [{
        label: "Account",
        icon: "user",
        onClick: () => setScreen("account")
      }, {
        label: "API tokens",
        icon: "key",
        onClick: () => setScreen("account")
      }, {
        label: "Toggle offline demo",
        icon: "wifi-off",
        onClick: () => setOffline(o => !o)
      }, {
        label: "Sign out",
        icon: "log-out",
        danger: true,
        onClick: () => setScreen("login")
      }]
    }))
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(SideNav, {
    links: links
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: "auto"
    }
  }, children)), /*#__PURE__*/React.createElement("div", {
    className: "mobile-only",
    style: {
      display: "none"
    }
  }, /*#__PURE__*/React.createElement(BottomNav, {
    links: links
  })));
}
function App() {
  const {
    useState,
    useEffect
  } = React;
  const [route, setRoute] = useState("login");
  const [screen, setScreen] = useState("dashboard");
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", "system");
  }, []);
  if (route === "login") return /*#__PURE__*/React.createElement(LoginScreen, {
    onLogin: () => setRoute("app")
  });
  if (route === "invite") return /*#__PURE__*/React.createElement(InviteScreen, {
    state: "pending",
    onAccept: () => setRoute("app")
  });
  if (route === "invite-expired") return /*#__PURE__*/React.createElement(InviteScreen, {
    state: "expired"
  });
  const screens = {
    dashboard: /*#__PURE__*/React.createElement(DashboardScreen, null),
    notes: /*#__PURE__*/React.createElement(NotesScreen, null),
    account: /*#__PURE__*/React.createElement(AccountScreen, null)
  };
  return /*#__PURE__*/React.createElement(AppShell, {
    screen: screen,
    setScreen: setScreen
  }, screens[screen], /*#__PURE__*/React.createElement("div", {
    style: {
      position: "fixed",
      bottom: 12,
      left: 12,
      display: "flex",
      gap: 6,
      zIndex: 100
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => setRoute("login"),
    style: {
      fontSize: 11,
      padding: "4px 8px",
      borderRadius: 6,
      border: "1px solid var(--color-border)",
      background: "var(--color-surface-raised)",
      color: "var(--color-text-muted)",
      cursor: "pointer"
    }
  }, "view: login"), /*#__PURE__*/React.createElement("button", {
    onClick: () => setRoute("invite"),
    style: {
      fontSize: 11,
      padding: "4px 8px",
      borderRadius: 6,
      border: "1px solid var(--color-border)",
      background: "var(--color-surface-raised)",
      color: "var(--color-text-muted)",
      cursor: "pointer"
    }
  }, "view: invite"), /*#__PURE__*/React.createElement("button", {
    onClick: () => setRoute("invite-expired"),
    style: {
      fontSize: 11,
      padding: "4px 8px",
      borderRadius: 6,
      border: "1px solid var(--color-border)",
      background: "var(--color-surface-raised)",
      color: "var(--color-text-muted)",
      cursor: "pointer"
    }
  }, "view: invite expired")));
}
ReactDOM.createRoot(document.getElementById("root")).render(/*#__PURE__*/React.createElement(App, null));
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/disp-client/App.jsx", error: String((e && e.message) || e) }); }

// ui_kits/disp-client/screens/AccountScreen.jsx
try { (() => {
function AccountScreen() {
  const {
    Tabs,
    TextField,
    SelectField,
    SecretField,
    Switch,
    Button,
    Dialog,
    Badge,
    IconButton,
    Icon
  } = window.DISPDesignSystem_bf3b97;
  const {
    useState
  } = React;
  const [tab, setTab] = useState(0);
  const [name, setName] = useState("Jordan Lee");
  const [theme, setTheme] = useState("system");
  const [createOpen, setCreateOpen] = useState(false);
  const [revealStep, setRevealStep] = useState(false);
  const [tokenName, setTokenName] = useState("");
  const tokens = [{
    name: "Home Assistant webhook",
    created: "2026-06-02",
    last: "2h ago"
  }, {
    name: "Backup script",
    created: "2026-04-11",
    last: "3d ago"
  }];
  const invites = [{
    email: "sam@household.example",
    status: "pending"
  }, {
    email: "kai@household.example",
    status: "accepted"
  }, {
    email: "old-invite@household.example",
    status: "expired"
  }];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 24,
      maxWidth: 720,
      display: "flex",
      flexDirection: "column",
      gap: 20
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: "1.5rem"
    }
  }, "Account"), /*#__PURE__*/React.createElement(Tabs, {
    tabs: ["Details", "API tokens", "Invites"],
    active: tab,
    onChange: setTab
  }), tab === 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 16,
      maxWidth: 420
    }
  }, /*#__PURE__*/React.createElement(TextField, {
    label: "Display name",
    value: name,
    onChange: setName
  }), /*#__PURE__*/React.createElement(TextField, {
    label: "Email",
    value: "jordan@household.example",
    disabled: true
  }), /*#__PURE__*/React.createElement(SelectField, {
    label: "Theme",
    value: theme,
    onChange: setTheme,
    options: [{
      label: "System",
      value: "system"
    }, {
      label: "Light",
      value: "light"
    }, {
      label: "Dark",
      value: "dark"
    }]
  }), /*#__PURE__*/React.createElement(Switch, {
    checked: true,
    onChange: () => {},
    label: "Show offline banner when disconnected"
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Button, {
    size: "sm"
  }, "Save changes"))), tab === 1 && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "flex-end"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    onClick: () => {
      setCreateOpen(true);
      setRevealStep(false);
      setTokenName("");
    }
  }, "Create token")), tokens.map(t => /*#__PURE__*/React.createElement("div", {
    key: t.name,
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "12px 14px",
      border: "1px solid var(--color-border)",
      borderRadius: 10,
      background: "var(--color-surface-raised)"
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 500,
      fontSize: "0.9375rem"
    }
  }, t.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "0.75rem",
      color: "var(--color-text-muted)"
    }
  }, "Created ", t.created, " · last used ", t.last)), /*#__PURE__*/React.createElement(IconButton, {
    label: "Revoke",
    variant: "secondary"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "trash-2"
  })))), /*#__PURE__*/React.createElement(Dialog, {
    open: createOpen,
    title: "Create API token",
    onClose: () => setCreateOpen(false),
    footer: revealStep ? /*#__PURE__*/React.createElement(Button, {
      onClick: () => setCreateOpen(false)
    }, "I've saved it") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Button, {
      variant: "ghost",
      onClick: () => setCreateOpen(false)
    }, "Cancel"), /*#__PURE__*/React.createElement(Button, {
      onClick: () => setRevealStep(true),
      disabled: !tokenName
    }, "Create"))
  }, !revealStep ? /*#__PURE__*/React.createElement(TextField, {
    label: "Token name",
    value: tokenName,
    onChange: setTokenName,
    placeholder: "e.g. Backup script"
  }) : /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8,
      alignItems: "center",
      padding: 8,
      background: "color-mix(in oklch, var(--color-warning) 12%, var(--color-surface-raised))",
      borderRadius: 8
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "triangle-alert",
    size: 16
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "0.8125rem"
    }
  }, "This is shown once. Copy it now — it can't be retrieved again.")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      fontFamily: "var(--font-mono)",
      fontSize: "0.8125rem",
      padding: "10px 12px",
      background: "var(--color-surface-sunken)",
      borderRadius: 6,
      border: "1px solid var(--color-border)",
      overflow: "hidden"
    }
  }, "disp_live_9f2a7c3e1b8d4f0a"), /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    variant: "secondary"
  }, "Copy"))))), tab === 2 && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, invites.map(i => /*#__PURE__*/React.createElement("div", {
    key: i.email,
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "10px 14px",
      border: "1px solid var(--color-border)",
      borderRadius: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "0.9375rem"
    }
  }, i.email), /*#__PURE__*/React.createElement(Badge, {
    tone: i.status === "accepted" ? "success" : i.status === "expired" ? "danger" : "neutral"
  }, i.status)))));
}
window.AccountScreen = AccountScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/disp-client/screens/AccountScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/disp-client/screens/DashboardScreen.jsx
try { (() => {
function DashboardScreen() {
  const {
    TileCard,
    TileItem,
    Badge,
    Button,
    EmptyState,
    ErrorView
  } = window.DISPDesignSystem_bf3b97;
  const {
    useState
  } = React;
  const [refreshedAt, setRefreshedAt] = useState("2m ago");
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
      gap: 16,
      padding: 20
    }
  }, /*#__PURE__*/React.createElement(TileCard, {
    title: "Uptime monitor",
    icon: "activity",
    onRefresh: () => setRefreshedAt("just now")
  }, /*#__PURE__*/React.createElement(TileItem, {
    primary: "api.home.local",
    secondary: `Updated ${refreshedAt}`,
    badge: /*#__PURE__*/React.createElement(Badge, {
      tone: "success"
    }, "Up")
  }), /*#__PURE__*/React.createElement(TileItem, {
    primary: "nas.home.local",
    secondary: "99.2% / 30d",
    badge: /*#__PURE__*/React.createElement(Badge, {
      tone: "danger"
    }, "Down")
  }), /*#__PURE__*/React.createElement(TileItem, {
    primary: "printer.home.local",
    secondary: "99.9% / 30d",
    badge: /*#__PURE__*/React.createElement(Badge, {
      tone: "success"
    }, "Up")
  })), /*#__PURE__*/React.createElement(TileCard, {
    title: "Notes",
    icon: "file-text",
    onRefresh: () => {},
    actions: /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      variant: "secondary"
    }, "Open Notes")
  }, /*#__PURE__*/React.createElement(TileItem, {
    primary: "Router config backup",
    secondary: "Edited yesterday"
  }), /*#__PURE__*/React.createElement(TileItem, {
    primary: "Guest wifi password",
    secondary: "Edited 4d ago"
  })), /*#__PURE__*/React.createElement(TileCard, {
    title: "Backups",
    icon: "database",
    state: "loading",
    onRefresh: () => {}
  }), /*#__PURE__*/React.createElement(TileCard, {
    title: "Weather",
    icon: "cloud",
    onRefresh: () => {}
  }, /*#__PURE__*/React.createElement(TileItem, {
    primary: "61°F, overcast",
    secondary: "Updated 12m ago"
  })), /*#__PURE__*/React.createElement(TileCard, {
    title: "Storage",
    icon: "hard-drive"
  }, /*#__PURE__*/React.createElement(EmptyState, {
    icon: "hard-drive",
    title: "No devices configured",
    description: "Add a device to see storage usage here."
  })), /*#__PURE__*/React.createElement(TileCard, {
    title: "Calendar",
    icon: "calendar",
    onRefresh: () => {}
  }, /*#__PURE__*/React.createElement(ErrorView, {
    message: "Couldn't reach calendar source.",
    onRetry: () => {}
  })));
}
window.DashboardScreen = DashboardScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/disp-client/screens/DashboardScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/disp-client/screens/LoginScreen.jsx
try { (() => {
function AuthLayout({
  children
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      height: "100%",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "var(--color-surface)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 360,
      display: "flex",
      flexDirection: "column",
      gap: 24
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 700,
      fontSize: "1.25rem",
      letterSpacing: "-0.01em"
    }
  }, "DISP"), children));
}
function LoginScreen({
  onLogin
}) {
  const {
    TextField,
    Button
  } = window.DISPDesignSystem_bf3b97;
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  return /*#__PURE__*/React.createElement(AuthLayout, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: "1.25rem"
    }
  }, "Sign in"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: "0.875rem",
      color: "var(--color-text-muted)",
      margin: 0
    }
  }, "Contact your admin if you don't have an account or need a password reset.")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement(TextField, {
    label: "Email",
    type: "email",
    value: email,
    onChange: setEmail,
    placeholder: "you@example.com"
  }), /*#__PURE__*/React.createElement(TextField, {
    label: "Password",
    type: "password",
    value: password,
    onChange: setPassword
  })), /*#__PURE__*/React.createElement(Button, {
    onClick: onLogin
  }, "Sign in"));
}
function InviteScreen({
  state,
  onAccept
}) {
  const {
    TextField,
    Button,
    Icon
  } = window.DISPDesignSystem_bf3b97;
  const {
    useState
  } = React;
  const [password, setPassword] = useState("");
  if (state === "expired" || state === "used" || state === "not-found") {
    const copy = {
      expired: ["Invite expired", "This invite link is no longer valid. Ask your admin to send a new one."],
      used: ["Invite already used", "This invite has already been accepted. Sign in instead."],
      "not-found": ["Invite not found", "Check the link your admin sent — it may have been mistyped."]
    }[state];
    return /*#__PURE__*/React.createElement(AuthLayout, null, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        gap: 8
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 40,
        height: 40,
        borderRadius: 10,
        background: "color-mix(in oklch, var(--color-danger) 14%, var(--color-surface-raised))",
        color: "var(--color-danger)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center"
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "triangle-alert",
      size: 20
    })), /*#__PURE__*/React.createElement("h1", {
      style: {
        fontSize: "1.125rem"
      }
    }, copy[0]), /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: "0.875rem",
        color: "var(--color-text-muted)",
        margin: 0
      }
    }, copy[1])));
  }
  return /*#__PURE__*/React.createElement(AuthLayout, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: "1.25rem"
    }
  }, "Accept invite"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: "0.875rem",
      color: "var(--color-text-muted)",
      margin: 0
    }
  }, "jordan@household.example — set a password to finish.")), /*#__PURE__*/React.createElement(TextField, {
    label: "Password",
    type: "password",
    value: password,
    onChange: setPassword
  }), /*#__PURE__*/React.createElement(Button, {
    onClick: onAccept
  }, "Create account"));
}
Object.assign(window, {
  LoginScreen,
  InviteScreen
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/disp-client/screens/LoginScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/disp-client/screens/NotesScreen.jsx
try { (() => {
function NotesScreen() {
  const {
    TextField,
    Button,
    Tag,
    Dialog,
    IconButton,
    Icon,
    EmptyState
  } = window.DISPDesignSystem_bf3b97;
  const {
    useState
  } = React;
  const notes = [{
    id: 1,
    title: "Router config backup",
    tags: ["network"],
    body: "Backup taken 2026-07-20. Config stored at /srv/backups/router-2026-07-20.cfg. Admin password rotated same day — see API tokens for the webhook key used by the rotation script."
  }, {
    id: 2,
    title: "Guest wifi password",
    tags: ["network", "shared"],
    body: "SSID: HouseholdGuest. Password rotates monthly, first of the month. Current password shared via the sharing link below — do not text it."
  }, {
    id: 3,
    title: "Recipe: sourdough starter feed ratio",
    tags: ["personal"],
    body: "1:1:1 starter:flour:water by weight, room temp. Feed every 12h in summer, 24h in winter."
  }];
  const [query, setQuery] = useState("");
  const [activeId, setActiveId] = useState(1);
  const [shareOpen, setShareOpen] = useState(false);
  const filtered = notes.filter(n => n.title.toLowerCase().includes(query.toLowerCase()));
  const active = notes.find(n => n.id === activeId);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      height: "100%"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 280,
      borderRight: "1px solid var(--color-border)",
      display: "flex",
      flexDirection: "column",
      padding: 16,
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement(TextField, {
    label: "",
    value: query,
    onChange: setQuery,
    placeholder: "Search notes…"
  })), /*#__PURE__*/React.createElement(IconButton, {
    label: "New note",
    variant: "secondary"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "plus"
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 2,
      overflowY: "auto"
    }
  }, filtered.length === 0 ? /*#__PURE__*/React.createElement(EmptyState, {
    icon: "search",
    title: "No matches",
    description: "Try a different search term."
  }) : filtered.map(n => /*#__PURE__*/React.createElement("button", {
    key: n.id,
    onClick: () => setActiveId(n.id),
    style: {
      textAlign: "left",
      border: "none",
      cursor: "pointer",
      padding: "10px 10px",
      borderRadius: 8,
      background: n.id === activeId ? "var(--color-surface-sunken)" : "transparent"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "0.9375rem",
      fontWeight: 500,
      color: "var(--color-text)"
    }
  }, n.title), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 4,
      marginTop: 4
    }
  }, n.tags.map(t => /*#__PURE__*/React.createElement("span", {
    key: t,
    style: {
      fontSize: 11,
      color: "var(--color-text-muted)",
      background: "var(--color-surface-raised)",
      border: "1px solid var(--color-border)",
      borderRadius: 4,
      padding: "1px 6px"
    }
  }, t))))))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      padding: 24,
      display: "flex",
      flexDirection: "column",
      gap: 16,
      maxWidth: "68ch"
    }
  }, active && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: "1.25rem"
    }
  }, active.title), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    variant: "secondary",
    onClick: () => setShareOpen(true)
  }, "Share"), /*#__PURE__*/React.createElement(IconButton, {
    label: "More"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "more-horizontal"
  })))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 6
    }
  }, active.tags.map(t => /*#__PURE__*/React.createElement(Tag, {
    key: t
  }, t))), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: "0.9375rem",
      lineHeight: 1.5,
      color: "var(--color-text)",
      margin: 0
    }
  }, active.body), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: "auto",
      fontSize: "0.75rem",
      color: "var(--color-text-muted)",
      display: "flex",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("span", null, "⌘K search"), /*#__PURE__*/React.createElement("span", null, "⌘N new"), /*#__PURE__*/React.createElement("span", null, "⌘S share")))), /*#__PURE__*/React.createElement(Dialog, {
    open: shareOpen,
    title: "Share note",
    onClose: () => setShareOpen(false),
    footer: /*#__PURE__*/React.createElement(Button, {
      onClick: () => setShareOpen(false)
    }, "Done")
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: "0.875rem",
      color: "var(--color-text-muted)",
      margin: 0
    }
  }, "Anyone with this link and household access can view this note."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      fontFamily: "var(--font-mono)",
      fontSize: "0.8125rem",
      padding: "10px 12px",
      background: "var(--color-surface-sunken)",
      borderRadius: 6,
      border: "1px solid var(--color-border)",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, "https://disp.local/n/8f2a-91c/share"), /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    variant: "secondary"
  }, "Copy")))));
}
window.NotesScreen = NotesScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/disp-client/screens/NotesScreen.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Avatar = __ds_scope.Avatar;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Icon = __ds_scope.Icon;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.Tag = __ds_scope.Tag;

__ds_ns.TileItem = __ds_scope.TileItem;

__ds_ns.TileCard = __ds_scope.TileCard;

__ds_ns.EmptyState = __ds_scope.EmptyState;

__ds_ns.ErrorView = __ds_scope.ErrorView;

__ds_ns.OfflineBanner = __ds_scope.OfflineBanner;

__ds_ns.SkeletonBlock = __ds_scope.SkeletonBlock;

__ds_ns.Toast = __ds_scope.Toast;

__ds_ns.SecretField = __ds_scope.SecretField;

__ds_ns.SelectField = __ds_scope.SelectField;

__ds_ns.Switch = __ds_scope.Switch;

__ds_ns.TextField = __ds_scope.TextField;

__ds_ns.BottomNav = __ds_scope.BottomNav;

__ds_ns.SideNav = __ds_scope.SideNav;

__ds_ns.Tabs = __ds_scope.Tabs;

__ds_ns.TopBar = __ds_scope.TopBar;

__ds_ns.Dialog = __ds_scope.Dialog;

__ds_ns.Menu = __ds_scope.Menu;

__ds_ns.Tooltip = __ds_scope.Tooltip;

})();
