/* Native XInput 2.4 gestures for the XFCE/X11 session. No evdev access. */
#define _POSIX_C_SOURCE 200809L
#include <X11/Xatom.h>
#include <X11/Xlib.h>
#include <X11/extensions/XInput2.h>
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <time.h>
#include <unistd.h>

typedef struct { int fingers; double x, y; } Swipe;
static volatile sig_atomic_t running = 1;
static void stop(int signal_number) { (void)signal_number; running = 0; }
static double animation_until = 0;

static double monotonic_seconds(void) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return now.tv_sec + now.tv_nsec / 1e9;
}

/* Clients may disappear while we annotate the workspace transition. */
static int x_error(Display *display, XErrorEvent *event) {
    if (event->error_code != BadWindow) {
        char message[128];
        XGetErrorText(display, event->error_code, message, sizeof(message));
        fprintf(stderr, "X11: %s (request %d)\n", message, event->request_code);
    }
    return 0;
}

static void animation_marker(Display *display, int step) {
    Atom list = XInternAtom(display, "_NET_CLIENT_LIST", True), type;
    Atom property = XInternAtom(display, "_KALI_WORKSPACE_DIRECTION", False);
    Atom desktop = XInternAtom(display, "_NET_WM_DESKTOP", False);
    int format; unsigned long count, remaining; unsigned char *data = NULL;
    if (!list || XGetWindowProperty(display, DefaultRootWindow(display), list, 0,
        65536, False, XA_WINDOW, &type, &format, &count, &remaining, &data) != Success)
        return;
    if (type == XA_WINDOW && format == 32) {
        Window *clients = (Window *)data;
        unsigned long value = step > 0 ? 1 : 2;
        for (unsigned long i = 0; i < count; i++) {
            if (!step) { XDeleteProperty(display, clients[i], property); continue; }
            Atom dt; int df; unsigned long dn, dr; unsigned char *dd = NULL;
            int status = XGetWindowProperty(display, clients[i], desktop, 0, 1,
                False, XA_CARDINAL, &dt, &df, &dn, &dr, &dd);
            int sticky = status == Success && dt == XA_CARDINAL && df == 32 && dn == 1
                && *(unsigned long *)dd == 0xffffffffUL;
            if (dd) XFree(dd);
            if (!sticky)
                XChangeProperty(display, clients[i], property, XA_CARDINAL, 32,
                                PropModeReplace, (unsigned char *)&value, 1);
        }
    }
    if (data) XFree(data);
    XSync(display, False);
    animation_until = step ? monotonic_seconds() + 0.35 : 0;
}

/* One switch on release, for deliberate horizontal gestures only. */
static int direction(Swipe s, int fingers, double threshold, int cancelled) {
    if (cancelled || s.fingers != fingers || fabs(s.x) < threshold ||
        fabs(s.x) < 1.5 * fabs(s.y)) return 0;
    return s.x < 0 ? 1 : -1; /* content moves left -> next workspace */
}

static long destination(long current, long count, int step, int wrap) {
    if (count < 1 || current < 0 || current >= count) return current;
    long next = current + step;
    if (next < 0) return wrap ? count - 1 : current;
    if (next >= count) return wrap ? 0 : current;
    return next;
}

static void self_test(void) {
    assert(direction((Swipe){4, -100, 10}, 4, 60, 0) == 1);
    assert(direction((Swipe){4, 100, -10}, 4, 60, 0) == -1);
    assert(direction((Swipe){3, -100, 0}, 4, 60, 0) == 0);
    assert(direction((Swipe){4, -100, 0}, 4, 60, 1) == 0);
    assert(direction((Swipe){4, -30, 0}, 4, 60, 0) == 0);
    assert(direction((Swipe){4, -100, 100}, 4, 60, 0) == 0);
    assert(destination(0, 4, -1, 0) == 0);
    assert(destination(3, 4, 1, 0) == 3);
    assert(destination(0, 4, -1, 1) == 3);
    assert(destination(3, 4, 1, 1) == 0);
    assert(destination(1, 4, 1, 0) == 2);
    puts("Gesture filtering, cancellation, directions and workspace boundaries passed.");
}

static void json_string(const char *s) {
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
        if (*p == '"' || *p == '\\') printf("\\%c", *p);
        else if (*p < 32) printf("\\u%04x", *p);
        else putchar(*p);
    }
    putchar('"');
}

static int natural_scroll(Display *display, int device) {
    Atom prop = XInternAtom(display, "libinput Natural Scrolling Enabled", True), type;
    int format; unsigned long count, remaining; unsigned char *data = NULL;
    if (!prop) return -1;
    int status = XIGetProperty(display, device, prop, 0, 1, False, AnyPropertyType,
                              &type, &format, &count, &remaining, &data);
    int result = status == Success && count == 1 && format == 8 ? data[0] : -1;
    if (data) XFree(data);
    return result;
}

static int gesture_touches(const XIDeviceInfo *device) {
    for (int i = 0; i < device->num_classes; i++)
        if (device->classes[i]->type == XIGestureClass)
            return ((XIGestureClassInfo *)device->classes[i])->num_touches;
    return 0;
}

static int find_device(Display *display, const char *name, int fingers) {
    int count, id = -1; XIDeviceInfo *devices = XIQueryDevice(display, XIAllDevices, &count);
    for (int i = 0; i < count; i++)
        if (devices[i].use == XISlavePointer && devices[i].enabled &&
            strcmp(devices[i].name, name) == 0 && gesture_touches(&devices[i]) >= fingers)
            id = devices[i].deviceid;
    XIFreeDeviceInfo(devices);
    return id;
}

static void inspect(Display *display) {
    int count, printed = 0; XIDeviceInfo *devices = XIQueryDevice(display, XIAllDevices, &count);
    puts("[");
    for (int i = 0; i < count; i++) {
        if (devices[i].use != XISlavePointer) continue;
        if (printed++) puts(",");
        printf("  {\"id\":%d,\"name\":", devices[i].deviceid);
        json_string(devices[i].name);
        printf(",\"natural_scrolling\":%d,\"gesture_touches\":%d}",
               natural_scroll(display, devices[i].deviceid), gesture_touches(&devices[i]));
    }
    puts("\n]"); XIFreeDeviceInfo(devices);
}

static long root_number(Display *display, const char *name) {
    Atom prop = XInternAtom(display, name, True), type; int format;
    unsigned long count, remaining; unsigned char *data = NULL;
    if (!prop) return -1;
    int status = XGetWindowProperty(display, DefaultRootWindow(display), prop, 0, 1,
        False, XA_CARDINAL, &type, &format, &count, &remaining, &data);
    long result = status == Success && type == XA_CARDINAL && format == 32 && count == 1
        ? (long)*(unsigned long *)data : -1;
    if (data) XFree(data);
    return result;
}

static int switch_workspace(Display *display, int step, int wrap, Time timestamp, int animate) {
    long current = root_number(display, "_NET_CURRENT_DESKTOP");
    long count = root_number(display, "_NET_NUMBER_OF_DESKTOPS");
    if (current < 0 || count < 1) { fputs("Workspace properties unavailable.\n", stderr); return 1; }
    long next = destination(current, count, step, wrap);
    if (next == current) return 0;
    if (animate) {
        animation_marker(display, step);
        /* Let the compositor process its rule property before windows unmap. */
        struct timespec pause = {0, 20000000};
        nanosleep(&pause, NULL);
    }
    XEvent event = {0}; event.xclient.type = ClientMessage;
    event.xclient.window = DefaultRootWindow(display);
    event.xclient.message_type = XInternAtom(display, "_NET_CURRENT_DESKTOP", False);
    event.xclient.format = 32;
    event.xclient.data.l[0] = next; event.xclient.data.l[1] = timestamp;
    if (!XSendEvent(display, DefaultRootWindow(display), False,
                   SubstructureNotifyMask | SubstructureRedirectMask, &event)) return 1;
    XFlush(display);
    printf("Workspace %ld -> %ld\n", current + 1, next + 1); fflush(stdout);
    return 0;
}

int main(int argc, char **argv) {
    const char *mode = "--run", *device = NULL, *lockfile = NULL;
    int fingers = 4, wrap = 0, inverse = 0, animate = 0; double threshold = 60;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--self-test")) { self_test(); return 0; }
        if (!strcmp(argv[i], "--inspect") || !strcmp(argv[i], "--probe") ||
            !strcmp(argv[i], "--next") || !strcmp(argv[i], "--previous")) mode = argv[i];
        else if (!strcmp(argv[i], "--device") && i + 1 < argc) device = argv[++i];
        else if (!strcmp(argv[i], "--fingers") && i + 1 < argc) fingers = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--threshold") && i + 1 < argc) threshold = atof(argv[++i]);
        else if (!strcmp(argv[i], "--lockfile") && i + 1 < argc) lockfile = argv[++i];
        else if (!strcmp(argv[i], "--wrap")) wrap = 1;
        else if (!strcmp(argv[i], "--inverse")) inverse = 1;
        else if (!strcmp(argv[i], "--animate")) animate = 1;
        else { fprintf(stderr, "Unknown or incomplete option: %s\n", argv[i]); return 2; }
    }
    if (fingers < 3 || fingers > 5 || !isfinite(threshold) || threshold <= 0) return 2;
    Display *display = XOpenDisplay(NULL);
    if (!display) { fputs("Cannot connect to the X11 session.\n", stderr); return 1; }
    XSetErrorHandler(x_error);
    int major = 2, minor = 4, opcode, event_number, error_number;
    if (!XQueryExtension(display, "XInputExtension", &opcode, &event_number, &error_number) ||
        XIQueryVersion(display, &major, &minor) != Success || major < 2 || (major == 2 && minor < 4)) {
        fputs("XInput 2.4 is required.\n", stderr); XCloseDisplay(display); return 1;
    }
    if (!strcmp(mode, "--inspect")) { inspect(display); XCloseDisplay(display); return 0; }
    if (!strcmp(mode, "--next") || !strcmp(mode, "--previous")) {
        int result = switch_workspace(display, !strcmp(mode, "--next") ? 1 : -1,
                                      wrap, CurrentTime, animate);
        if (animate) {
            struct timespec pause = {0, 350000000}; nanosleep(&pause, NULL);
            animation_marker(display, 0);
        }
        XCloseDisplay(display); return result;
    }
    if (!device) { fputs("--device is required.\n", stderr); XCloseDisplay(display); return 2; }
    int sourceid = find_device(display, device, fingers);
    if (sourceid < 0) { fputs("No matching touchpad with gesture support.\n", stderr); XCloseDisplay(display); return 1; }
    int lockfd = -1;
    if (lockfile) {
        lockfd = open(lockfile, O_CREAT | O_RDWR | O_CLOEXEC, 0600);
        if (lockfd < 0 || flock(lockfd, LOCK_EX | LOCK_NB) != 0) {
            fputs("Gesture listener already running, or lock unavailable.\n", stderr);
            XCloseDisplay(display); if (lockfd >= 0) close(lockfd); return 1;
        }
    }
    unsigned char bits[XIMaskLen(XI_LASTEVENT)] = {0};
    XISetMask(bits, XI_GestureSwipeBegin); XISetMask(bits, XI_GestureSwipeUpdate); XISetMask(bits, XI_GestureSwipeEnd);
    XIEventMask mask = {XIAllMasterDevices, sizeof(bits), bits};
    XIGrabModifiers mods = {(int)XIAnyModifier, 0};
    /* Inspect the beginning synchronously, then replay all gestures we don't own.
     * The paired keyboard stays asynchronous throughout. */
    int result = XIGrabSwipeGestureBegin(display, XIAllMasterDevices, DefaultRootWindow(display),
        XIGrabModeSync, XIGrabModeAsync, False, &mask, 1, &mods);
    XSync(display, False);
    if (result != Success || mods.status != GrabSuccess) {
        fprintf(stderr, "Could not register swipe gestures: result=%d status=%d\n", result, mods.status);
        XCloseDisplay(display); if (lockfd >= 0) close(lockfd); return 1;
    }
    printf("Ready: %d-finger swipes on %s; threshold %.0f; wrap %d.\n", fingers, device, threshold, wrap);
    fflush(stdout);
    if (!strcmp(mode, "--probe")) { XCloseDisplay(display); if (lockfd >= 0) close(lockfd); return 0; }
    signal(SIGTERM, stop); signal(SIGINT, stop);
    Swipe swipe = {0}; int active_device = -1;
    while (running) {
        if (animation_until && monotonic_seconds() >= animation_until)
            animation_marker(display, 0);
        if (!XPending(display)) {
            struct pollfd fd = {ConnectionNumber(display), POLLIN, 0};
            int ready = poll(&fd, 1, animation_until ? 20 : 1000);
            if (ready < 0 && errno != EINTR) break;
            if (ready <= 0) continue;
        }
        XEvent event; XNextEvent(display, &event);
        if (event.type != GenericEvent || event.xcookie.extension != opcode ||
            !XGetEventData(display, &event.xcookie)) continue;
        int type = event.xcookie.evtype;
        if (type >= XI_GestureSwipeBegin && type <= XI_GestureSwipeEnd) {
            XIGestureSwipeEvent *gesture = event.xcookie.data;
            if (type == XI_GestureSwipeBegin) {
                int ours = gesture->sourceid == sourceid && gesture->detail == fingers;
                XIAllowEvents(display, gesture->deviceid, ours ? XIAsyncDevice : XIReplayDevice, gesture->time);
                XFlush(display);
                if (ours) { swipe = (Swipe){gesture->detail, 0, 0}; active_device = gesture->deviceid; }
            } else if (gesture->deviceid == active_device) {
                swipe.x += gesture->delta_x; swipe.y += gesture->delta_y;
                if (type == XI_GestureSwipeEnd) {
                    int step = direction(swipe, fingers, threshold, gesture->flags & XIGestureSwipeEventCancelled);
                    if (step) switch_workspace(display, inverse ? -step : step, wrap, gesture->time, animate);
                    active_device = -1; swipe = (Swipe){0};
                }
            }
        }
        XFreeEventData(display, &event.xcookie);
    }
    if (animate) animation_marker(display, 0);
    XCloseDisplay(display); if (lockfd >= 0) close(lockfd); return 0;
}
