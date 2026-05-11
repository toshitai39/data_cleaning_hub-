import { Box, Typography, Avatar, Button } from '@mui/material';
import LogoutIcon from '@mui/icons-material/Logout';
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import InsightsOutlinedIcon from '@mui/icons-material/InsightsOutlined';
import AutoFixHighOutlinedIcon from '@mui/icons-material/AutoFixHighOutlined';
import VerifiedOutlinedIcon from '@mui/icons-material/VerifiedOutlined';
import ContentCopyOutlinedIcon from '@mui/icons-material/ContentCopyOutlined';
import CompareArrowsOutlinedIcon from '@mui/icons-material/CompareArrowsOutlined';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import { useAuth } from '../context/AuthContext.jsx';
import { UNIQUS } from '../theme.js';

export const STAGES = [
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
    ],
  },
  {
    section: 'RULES & QUALITY',
    steps: [
      { key: 'rules', label: 'Rule generator', icon: AutoFixHighOutlinedIcon },
      { key: 'quality', label: 'Data quality', icon: VerifiedOutlinedIcon },
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

function StepRow({ icon: Icon, label, active, onClick }) {
  return (
    <Box
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); }}
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.25,
        px: 1.5,
        py: 1,
        mb: 0.5,
        borderRadius: 1.25,
        cursor: 'pointer',
        borderLeft: '3px solid',
        borderColor: active ? 'primary.main' : 'transparent',
        bgcolor: active ? 'rgba(91,26,120,0.10)' : 'transparent',
        color: active ? 'primary.main' : 'text.primary',
        transition: 'background-color 120ms, border-color 120ms',
        '&:hover': {
          bgcolor: active ? 'rgba(91,26,120,0.14)' : 'rgba(0,0,0,0.04)',
        },
      }}
    >
      <Icon fontSize="small" sx={{ color: active ? 'primary.main' : 'text.secondary' }} />
      <Typography variant="body2" sx={{ fontWeight: active ? 600 : 500 }}>
        {label}
      </Typography>
    </Box>
  );
}

export default function Sidebar({ activeKey, onSelect }) {
  const { user, logout } = useAuth();
  const initials = (user?.name || user?.username || 'U').slice(0, 2).toUpperCase();

  return (
    <Box
      component="aside"
      sx={{
        width: 280,
        flexShrink: 0,
        bgcolor: '#faf7fb',
        borderRight: '1px solid',
        borderColor: 'divider',
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        position: 'sticky',
        top: 0,
      }}
    >
      <Box sx={{ background: UNIQUS.gradient, p: 2, textAlign: 'center' }}>
        <Box
          component="img"
          src="/assets/uniqus_logo.png"
          alt="Uniqus"
          sx={{
            height: 28,
            display: 'block',
            mx: 'auto',
            mb: 0.5,
            filter: 'brightness(0) invert(1)',
          }}
        />
        <Typography variant="subtitle2" sx={{ color: 'white', fontWeight: 700, letterSpacing: 0.3 }}>
          Master Data Profiler
        </Typography>
        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.85)' }}>
          Enterprise Data Quality
        </Typography>
      </Box>

      <Box
        sx={{
          p: 1.75,
          display: 'flex',
          alignItems: 'center',
          gap: 1.25,
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Avatar
          sx={{
            background: UNIQUS.gradientSoft,
            width: 36,
            height: 36,
            fontWeight: 700,
            fontSize: 14,
          }}
        >
          {initials}
        </Avatar>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body2" noWrap sx={{ fontWeight: 600 }}>
            {user?.name || user?.username}
          </Typography>
          <Typography variant="caption" color="text.secondary">Authenticated</Typography>
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflowY: 'auto', p: 1.5 }}>
        <Typography
          variant="caption"
          sx={{
            color: 'text.secondary',
            fontWeight: 700,
            letterSpacing: 1.1,
            display: 'block',
            ml: 1,
            mb: 1,
          }}
        >
          PROFILER · PIPELINE
        </Typography>
        <Box sx={{ borderTop: '1px solid', borderColor: 'divider', mb: 1.5 }} />

        {STAGES.map((stage) => (
          <Box key={stage.section} sx={{ mb: 1.5 }}>
            <Box
              sx={{
                bgcolor: 'rgba(91,26,120,0.06)',
                px: 1.5,
                py: 0.6,
                mb: 0.75,
                borderRadius: 1,
              }}
            >
              <Typography
                variant="caption"
                sx={{ fontWeight: 700, letterSpacing: 0.8, color: 'text.secondary' }}
              >
                {stage.section}
              </Typography>
            </Box>
            {stage.steps.map((step) => (
              <StepRow
                key={step.key}
                icon={step.icon}
                label={step.label}
                active={step.key === activeKey}
                onClick={() => onSelect(step.key)}
              />
            ))}
          </Box>
        ))}
      </Box>

      <Box sx={{ p: 1.5, borderTop: '1px solid', borderColor: 'divider' }}>
        <Button variant="outlined" startIcon={<LogoutIcon />} onClick={logout} fullWidth size="small">
          Sign out
        </Button>
      </Box>
    </Box>
  );
}
