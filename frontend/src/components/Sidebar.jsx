import {
  Box, Typography, Avatar, Stack, Button, Divider, Chip,
} from '@mui/material';
import LogoutIcon from '@mui/icons-material/Logout';
import StorageIcon from '@mui/icons-material/Storage';
import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import VerifiedIcon from '@mui/icons-material/Verified';
import HistoryIcon from '@mui/icons-material/History';
import { useAuth } from '../context/AuthContext.jsx';
import { useDataset } from '../context/DatasetContext.jsx';
import { UNIQUS } from '../theme.js';

function Stat({ icon, label, value }) {
  return (
    <Box
      sx={{
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 2,
        p: 1.25,
        textAlign: 'center',
      }}
    >
      <Stack direction="row" justifyContent="center" alignItems="center" spacing={0.5}>
        {icon}
        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}>
          {label}
        </Typography>
      </Stack>
      <Typography variant="h6" sx={{ color: 'primary.main', fontWeight: 700, mt: 0.5 }}>
        {value}
      </Typography>
    </Box>
  );
}

export default function Sidebar() {
  const { user, logout } = useAuth();
  const { state } = useDataset();

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
        p: 2.5,
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      <Box
        sx={{
          background: UNIQUS.gradient,
          borderRadius: 0,
          p: 2.5,
          color: 'white',
          textAlign: 'center',
          boxShadow: '0 6px 20px rgba(91,26,120,0.25)',
        }}
      >
        <Box
          component="img"
          src="/assets/uniqus_logo.png"
          alt="Uniqus"
          sx={{
            height: 36,
            width: 'auto',
            display: 'block',
            mx: 'auto',
            mb: 1.25,
            filter: 'brightness(0) invert(1)',
          }}
        />
        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'white', letterSpacing: 0.3 }}>
          Master Data Profiler
        </Typography>
        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.85)' }}>
          Enterprise Data Quality
        </Typography>
      </Box>

      <Box
        sx={{
          bgcolor: 'background.paper',
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2,
          p: 1.5,
          display: 'flex',
          alignItems: 'center',
          gap: 1.25,
        }}
      >
        <Avatar
          sx={{
            background: UNIQUS.gradientSoft,
            width: 40,
            height: 40,
            fontWeight: 700,
          }}
        >
          {initials}
        </Avatar>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle2" noWrap>{user?.name || user?.username}</Typography>
          <Typography variant="caption" color="text.secondary">Authenticated</Typography>
        </Box>
      </Box>

      <Divider sx={{ borderColor: 'divider' }} />

      <Typography variant="overline" color="text.secondary">Workspace</Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
        <Stat icon={<StorageIcon fontSize="small" sx={{ color: 'primary.main' }} />} label="Rows" value={state.rows.toLocaleString()} />
        <Stat icon={<ViewColumnIcon fontSize="small" sx={{ color: 'primary.main' }} />} label="Cols" value={state.columns} />
        <Stat
          icon={<VerifiedIcon fontSize="small" sx={{ color: 'primary.main' }} />}
          label="Quality"
          value={state.quality_score == null ? '—' : `${state.quality_score.toFixed(0)}`}
        />
        <Stat icon={<HistoryIcon fontSize="small" sx={{ color: 'primary.main' }} />} label="Ops" value={state.operations} />
      </Box>

      {state.filename && (
        <Chip
          size="small"
          label={state.filename}
          color="secondary"
          variant="outlined"
          sx={{ mt: 0.5, maxWidth: '100%', '& .MuiChip-label': { overflow: 'hidden', textOverflow: 'ellipsis' } }}
        />
      )}

      <Box sx={{ flex: 1 }} />

      <Button
        variant="outlined"
        startIcon={<LogoutIcon />}
        onClick={logout}
        fullWidth
      >
        Sign out
      </Button>
    </Box>
  );
}
