import { Box, Typography, Avatar, IconButton, Tooltip } from '@mui/material';
import { useProject } from '../context/ProjectContext.jsx';
import LogoutIcon from '@mui/icons-material/Logout';
import HomeOutlinedIcon from '@mui/icons-material/HomeOutlined';
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import InsightsOutlinedIcon from '@mui/icons-material/InsightsOutlined';
import AutoFixHighOutlinedIcon from '@mui/icons-material/AutoFixHighOutlined';
import VerifiedOutlinedIcon from '@mui/icons-material/VerifiedOutlined';
import ContentCopyOutlinedIcon from '@mui/icons-material/ContentCopyOutlined';
import CompareArrowsOutlinedIcon from '@mui/icons-material/CompareArrowsOutlined';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import { useAuth } from '../context/AuthContext.jsx';

export const STAGES = [
  {
    section: 'WORKSPACE',
    steps: [
      { key: 'home', label: 'Home', icon: HomeOutlinedIcon },
    ],
  },
  {
    section: 'DATA INPUT',
    steps: [
      { key: 'load', label: 'Load data', icon: UploadFileOutlinedIcon },
    ],
  },
  {
    section: 'PROFILE',
    steps: [
      { key: 'profile', label: 'Data profiling', icon: InsightsOutlinedIcon },
      // Dashboard sits AFTER profiling — it's a consumer of the
      // assessment, so navigating to it before scores exist makes no
      // sense. The new order matches the steward's actual workflow.
      { key: 'dashboard', label: 'Dashboard', icon: DashboardOutlinedIcon },
    ],
  },
  {
    section: 'RULES & CLEANSING',
    steps: [
      { key: 'rules', label: 'Rule generator', icon: AutoFixHighOutlinedIcon },
      { key: 'quality', label: 'Cleansing', icon: VerifiedOutlinedIcon },
      { key: 'dupes', label: 'Find duplicates', icon: ContentCopyOutlinedIcon },
    ],
  },
  {
    section: 'REVIEW & EXPORT',
    steps: [
      { key: 'compare', label: 'Compare', icon: CompareArrowsOutlinedIcon },
      { key: 'preview', label: 'Preview', icon: VisibilityOutlinedIcon },
      { key: 'export', label: 'Export', icon: FileDownloadOutlinedIcon },
    ],
  },
];

export const STAGE_KEYS = STAGES.flatMap((s) => s.steps.map((st) => st.key));

function StepRow({ icon: Icon, label, active, onClick, disabled, disabledReason }) {
  const inner = (
    <Box
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled || undefined}
      onClick={disabled ? undefined : onClick}
      onKeyDown={(e) => {
        if (disabled) return;
        if (e.key === 'Enter' || e.key === ' ') onClick();
      }}
      sx={{
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        px: 1.75,
        py: 1.1,
        mb: 0.4,
        borderRadius: 1.25,
        cursor: disabled ? 'not-allowed' : 'pointer',
        color: disabled
          ? 'rgba(255,255,255,0.32)'
          : active ? '#FFFFFF' : 'rgba(255,255,255,0.78)',
        bgcolor: !disabled && active ? 'rgba(255,255,255,0.10)' : 'transparent',
        fontWeight: active ? 600 : 500,
        opacity: disabled ? 0.85 : 1,
        transition: 'background-color 120ms, color 120ms',
        '&:hover': disabled ? {} : {
          bgcolor: active ? 'rgba(255,255,255,0.14)' : 'rgba(255,255,255,0.06)',
          color: '#FFFFFF',
        },
        '&::before': !disabled && active ? {
          content: '""',
          position: 'absolute',
          left: 6,
          top: '50%',
          transform: 'translateY(-50%)',
          width: 3,
          height: 22,
          background: '#C879AB',
          borderRadius: 2,
        } : {},
      }}
    >
      <Icon
        sx={{
          fontSize: 18,
          color: disabled
            ? 'rgba(255,255,255,0.28)'
            : active ? '#FFFFFF' : 'rgba(255,255,255,0.68)',
        }}
      />
      <Typography variant="body2" sx={{ fontWeight: 'inherit', fontSize: '0.84rem' }}>
        {label}
      </Typography>
    </Box>
  );
  if (disabled && disabledReason) {
    return (
      <Tooltip title={disabledReason} placement="right" arrow>
        <span>{inner}</span>
      </Tooltip>
    );
  }
  return inner;
}

export default function Sidebar({ activeKey, onSelect }) {
  const { user, logout } = useAuth();
  const { active: activeProject } = useProject();
  const initials = (user?.name || user?.username || 'U').slice(0, 2).toUpperCase();
  const hasProject = !!activeProject;
  // Keys that always work regardless of project state. Everything else
  // requires an active project — the user picks one from Home (or creates
  // a new analysis) before the data-dependent steps come alive.
  const ALWAYS_ENABLED = new Set(['home', 'new']);

  return (
    <Box
      component="aside"
      sx={{
        width: 260,
        flexShrink: 0,
        bgcolor: '#1B0E3D',
        color: '#FFFFFF',
        borderRight: '1px solid rgba(0,0,0,0.4)',
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        position: 'sticky',
        top: 0,
      }}
    >
      <Box sx={{
        px: 3,
        py: 3.5,
        borderBottom: '1px solid rgba(255,255,255,0.08)',
      }}>
        <Box
          component="img"
          src="/assets/uniqus_logo.png"
          alt="Uniqus"
          sx={{
            height: 32,
            display: 'block',
            mb: 1.5,
            filter: 'brightness(0) invert(1)',
          }}
        />
        <Typography
          sx={{
            fontFamily: "'Montserrat', sans-serif",
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.14em',
            color: 'rgba(160,150,194,1)',
            textTransform: 'uppercase',
          }}
        >
          Data Profiler · Pipeline
        </Typography>
      </Box>

      <Box sx={{ flex: 1, overflowY: 'auto', py: 1, px: 1.5 }}>
        {STAGES.map((stage) => (
          <Box key={stage.section} sx={{ mb: 1.25 }}>
            <Typography
              sx={{
                px: 1.25,
                pt: 1.5,
                pb: 0.75,
                fontFamily: "'Montserrat', sans-serif",
                fontSize: '10px',
                fontWeight: 700,
                letterSpacing: '0.16em',
                color: 'rgba(160,150,194,0.85)',
                textTransform: 'uppercase',
              }}
            >
              {stage.section}
            </Typography>
            {stage.steps.map((step) => {
              const stepDisabled = !ALWAYS_ENABLED.has(step.key) && !hasProject;
              return (
                <StepRow
                  key={step.key}
                  icon={step.icon}
                  label={step.label}
                  active={step.key === activeKey}
                  onClick={() => onSelect(step.key)}
                  disabled={stepDisabled}
                  disabledReason={
                    stepDisabled
                      ? 'Open or create a project on the Home page to enable this step.'
                      : undefined
                  }
                />
              );
            })}
          </Box>
        ))}
      </Box>

      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.25,
          px: 2,
          py: 1.75,
          borderTop: '1px solid rgba(255,255,255,0.08)',
        }}
      >
        <Avatar
          sx={{
            background: 'linear-gradient(135deg, #492079 0%, #B31E7C 100%)',
            width: 36,
            height: 36,
            fontWeight: 700,
            fontSize: 13,
          }}
        >
          {initials}
        </Avatar>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography
            sx={{ fontSize: 13, fontWeight: 600, color: '#FFFFFF', lineHeight: 1.2 }}
            noWrap
          >
            {user?.name || user?.username}
          </Typography>
          <Typography
            sx={{ fontSize: 11, color: 'rgba(160,150,194,1)' }}
            noWrap
          >
            Authenticated
          </Typography>
        </Box>
        <Tooltip title="Sign out">
          <IconButton
            onClick={logout}
            size="small"
            sx={{
              width: 34,
              height: 34,
              borderRadius: 1,
              bgcolor: 'rgba(255,255,255,0.08)',
              color: '#FFFFFF',
              border: '1px solid rgba(255,255,255,0.10)',
              '&:hover': { bgcolor: 'rgba(255,255,255,0.14)' },
            }}
          >
            <LogoutIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </Tooltip>
      </Box>
    </Box>
  );
}
