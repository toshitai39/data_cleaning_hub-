import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Stack,
  Typography, Divider, Box,
} from '@mui/material';

export default function RulesPopover({ open, onClose, column, rules, onEdit, onDelete }) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{column} — Rules ({rules.length})</DialogTitle>
      <DialogContent>
        {rules.length === 0 ? (
          <Typography variant="body2" color="text.secondary">No rules</Typography>
        ) : (
          <Stack spacing={1}>
            {rules.map((rule, idx) => (
              <Box key={idx}>
                <Typography variant="subtitle2">{idx + 1}. {rule.name}</Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>Mode: {rule.mode}</Typography>
                {rule.pattern && (
                  <Typography variant="caption" sx={{ display: 'block', fontFamily: 'monospace' }}>
                    Pattern: {rule.pattern}
                  </Typography>
                )}
                {rule.replace && (
                  <Typography variant="caption" sx={{ display: 'block', fontFamily: 'monospace' }}>
                    Replace: {rule.replace}
                  </Typography>
                )}
                {rule.mode === 'Case' && (
                  <Typography variant="caption" sx={{ display: 'block' }}>Case: {rule.case}</Typography>
                )}
                {rule.mode === 'Length' && (
                  <Typography variant="caption" sx={{ display: 'block' }}>Length: {rule.length_mode}</Typography>
                )}
                <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>
                  {rule.timestamp}
                </Typography>
                <Stack direction="row" spacing={1} mt={0.5}>
                  <Button size="small" variant="outlined" onClick={() => onEdit(idx)}>Edit</Button>
                  <Button size="small" variant="outlined" color="error" onClick={() => onDelete(idx)}>Delete</Button>
                </Stack>
                {idx < rules.length - 1 && <Divider sx={{ mt: 1 }} />}
              </Box>
            ))}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
