import { Box, Typography, Avatar, Chip } from '@mui/material';
import FolderOpenOutlinedIcon from '@mui/icons-material/FolderOpenOutlined';
import { useAuth } from '../context/AuthContext.jsx';
import { useProject } from '../context/ProjectContext.jsx';

const LABEL_BY_KEY = {
  home: 'Home',
  new: 'New analysis',
  load: 'Load data',
  dashboard: 'Dashboard',
  profile: 'Data profiling',
  rules: 'Rule generator',
  quality: 'Cleansing',
  dupes: 'Find duplicates',
  compare: 'Compare',
  preview: 'Preview',
  export: 'Export',
};

export default function TopBar({ activeKey }) {
  const { user } = useAuth();
  const { active: activeProject } = useProject();
  const initials = (user?.name || user?.username || 'U').slice(0, 2).toUpperCase();
  const current = LABEL_BY_KEY[activeKey] || activeKey;

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 2,
        px: 4,
        py: 2,
        bgcolor: '#FFFFFF',
        borderBottom: '1px solid #E7E6E6',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.25,
          fontSize: 14,
          color: '#555555',
          flexWrap: 'wrap',
        }}
      >
        <Typography component="span" sx={{ fontSize: 14, color: '#8A8A8A', fontWeight: 500 }}>
          Uniqus Consultech
        </Typography>
        <Typography component="span" sx={{ color: '#8A8A8A' }}>/</Typography>
        <Typography component="span" sx={{ fontSize: 14, color: '#8A8A8A', fontWeight: 500 }}>
          Data Profiler
        </Typography>
        {activeProject && (
          <>
            <Typography component="span" sx={{ color: '#8A8A8A' }}>/</Typography>
            <Chip
              size="small"
              icon={<FolderOpenOutlinedIcon sx={{ fontSize: 14 }} />}
              label={`${activeProject.system?.label || ''} · ${activeProject.stream?.label || ''}`}
              sx={{
                height: 22,
                fontSize: '0.72rem',
                fontWeight: 600,
                bgcolor: '#F4ECF9',
                color: '#6A28A8',
                '& .MuiChip-icon': { color: '#6A28A8' },
              }}
            />
          </>
        )}
        <Typography component="span" sx={{ color: '#8A8A8A' }}>/</Typography>
        <Typography component="span" sx={{ fontSize: 14, color: '#1A1A1A', fontWeight: 600 }}>
          {current}
        </Typography>
      </Box>

      <Box sx={{ ml: 'auto' }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1.25,
            pl: 0.75,
            pr: 1.75,
            py: 0.5,
            borderRadius: 999,
            bgcolor: '#F7F5FA',
            border: '1px solid #E7E6E6',
          }}
        >
          <Avatar
            sx={{
              width: 30,
              height: 30,
              fontSize: 12,
              fontWeight: 700,
              background: 'linear-gradient(135deg, #492079 0%, #B31E7C 100%)',
            }}
          >
            {initials}
          </Avatar>
          <Box sx={{ lineHeight: 1.1 }}>
            <Typography sx={{ fontSize: 13, fontWeight: 600, color: '#1A1A1A' }} noWrap>
              {user?.name || user?.username}
            </Typography>
            <Typography
              sx={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', color: '#8A8A8A' }}
            >
              MEMBER
            </Typography>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
