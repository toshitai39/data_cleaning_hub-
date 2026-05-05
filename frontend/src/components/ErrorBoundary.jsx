import { Component } from 'react';
import { Alert, Button, Box, Typography, Paper } from '@mui/material';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught:', error, info);
    this.setState({ info });
  }

  reset = () => this.setState({ error: null, info: null });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Box sx={{ p: 4 }}>
        <Paper sx={{ p: 4, maxWidth: 800, mx: 'auto' }}>
          <Alert severity="error" sx={{ mb: 2 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Something went wrong on this tab.
            </Typography>
            <Typography variant="body2" sx={{ mt: 1 }}>
              The page is still alive — switch tabs or click reset below.
            </Typography>
          </Alert>
          <Typography variant="caption" color="text.secondary"
            sx={{ display: 'block', fontFamily: 'monospace', whiteSpace: 'pre-wrap', mb: 2 }}>
            {String(this.state.error?.stack || this.state.error?.message || this.state.error)}
          </Typography>
          <Button variant="contained" onClick={this.reset}>Reset this tab</Button>
        </Paper>
      </Box>
    );
  }
}
