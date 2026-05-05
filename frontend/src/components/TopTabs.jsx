import { Tabs, Tab, Box } from '@mui/material';

export default function TopTabs({ tabs, value, onChange }) {
  return (
    <Box
      sx={{
        bgcolor: 'background.paper',
        borderBottom: '1px solid',
        borderColor: 'divider',
        position: 'sticky',
        top: 0,
        zIndex: 5,
      }}
    >
      <Tabs
        value={value}
        onChange={(_, v) => onChange(v)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ px: 2 }}
        TabIndicatorProps={{ sx: { height: 3, borderRadius: 2 } }}
      >
        {tabs.map((t) => (
          <Tab key={t} label={t} />
        ))}
      </Tabs>
    </Box>
  );
}
