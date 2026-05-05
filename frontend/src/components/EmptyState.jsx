import { Paper, Typography, Box } from '@mui/material';
import InboxOutlinedIcon from '@mui/icons-material/InboxOutlined';

export default function EmptyState({ title = 'No data loaded', message = 'Upload a dataset from the Load Data tab to begin.' }) {
  return (
    <Paper sx={{ p: 6, textAlign: 'center' }}>
      <Box
        sx={{
          width: 64, height: 64, borderRadius: '50%',
          bgcolor: 'action.hover', display: 'inline-flex',
          alignItems: 'center', justifyContent: 'center',
          mb: 2,
        }}
      >
        <InboxOutlinedIcon sx={{ fontSize: 32, color: 'text.secondary' }} />
      </Box>
      <Typography variant="h6">{title}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1, maxWidth: 460, mx: 'auto' }}>
        {message}
      </Typography>
    </Paper>
  );
}
