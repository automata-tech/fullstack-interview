# Lab Automation Interview Exercise - Quick Reference

## For the Interviewer

This is a 60-90 minute paired programming exercise for a Staff Full-Stack Engineer role.

### Setup (Before Interview)
```bash
docker-compose up --build
```

Verify all bugs are present by checking that Bug 2 prevents workflows from starting.

### Exercise Flow

**Phase 1: Debugging (30-40 min)**
Candidate fixes 4 bugs:
1. Missing `DEVICE_API_URL` env var → service crashes
2. Wrong API endpoint path → workflows fail to start
3. Race condition in device booking → run `./test-race-condition.sh` to demonstrate
4. Frontend status cache → device status doesn't update in UI

**Phase 2: Feature Implementation (30-50 min)**
Implement pause/resume workflow feature (backend + frontend)

### Quick Debugging

If candidate gets stuck:

**Bug 1**: Check `docker-compose logs workflow-service`
**Bug 2**: Look at the endpoint path in `workflow-service/app.py` line ~127
**Bug 3**: Run `./test-race-condition.sh` and check logs for multiple "successfully booked" messages
**Bug 4**: Check `DeviceList.js` - notice the status caching logic

### Evaluation Focus

✅ Systematic debugging approach (logs, tools)
✅ Full-stack competency (React + Python)
✅ Understanding of distributed systems
✅ Clean code and testing
✅ Communication and problem-solving

### Files to Review
- `README.md` - Candidate instructions
- `SOLUTION_GUIDE.md` - Complete solutions and fixes
- `test-race-condition.sh` - Script to reproduce Bug 3

### Key Artifacts
- Candidate should fix bugs in code
- Candidate should implement pause/resume endpoints + UI
- Check git commits for quality

---

## For the Candidate

See [README.md](README.md) for full instructions.

### Quick Start
```bash
docker-compose up --build
# Open http://localhost:3000
# Fix bugs, then implement pause/resume feature
```

### Key Commands
```bash
docker-compose logs -f workflow-service    # View service logs
./test-race-condition.sh                   # Test concurrency bug
docker-compose restart workflow-service    # Restart after changes
```
