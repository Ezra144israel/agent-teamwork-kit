#import <AVFoundation/AVFoundation.h>
#import <AppKit/AppKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <CoreVideo/CoreVideo.h>
#import <Foundation/Foundation.h>
#import <math.h>

static const int kFPS = 30;
static const int kDurationSeconds = 28;

static uint64_t UpdateFNV1a64(uint64_t hash, const uint8_t *bytes, size_t length) {
    for (size_t index = 0; index < length; index++) {
        hash ^= bytes[index];
        hash *= UINT64_C(1099511628211);
    }
    return hash;
}

static NSString *FNV1a64String(uint64_t hash) {
    return [NSString stringWithFormat:@"fnv1a64:%016llx", (unsigned long long)hash];
}

static NSDictionary *ReadEvidence(NSString *path) {
    NSData *data = [NSData dataWithContentsOfFile:path];
    if (!data) {
        @throw [NSException exceptionWithName:@"EvidenceError" reason:@"cannot read evidence" userInfo:nil];
    }
    NSError *error = nil;
    NSDictionary *value = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
    if (![value isKindOfClass:[NSDictionary class]] || error) {
        @throw [NSException exceptionWithName:@"EvidenceError" reason:@"invalid evidence JSON" userInfo:nil];
    }
    return value;
}

static NSFont *Mono(CGFloat size, NSFontWeight weight) {
    NSFont *font = [NSFont monospacedSystemFontOfSize:size weight:weight];
    return font ?: [NSFont fontWithName:@"Menlo" size:size];
}

static void DrawText(NSString *text, NSRect rect, CGFloat size, NSColor *color, NSFontWeight weight, NSTextAlignment alignment) {
    NSMutableParagraphStyle *style = [[NSMutableParagraphStyle alloc] init];
    style.alignment = alignment;
    style.lineBreakMode = NSLineBreakByWordWrapping;
    style.lineSpacing = size * 0.2;
    NSDictionary *attributes = @{
        NSFontAttributeName: Mono(size, weight),
        NSForegroundColorAttributeName: color,
        NSParagraphStyleAttributeName: style,
    };
    [text drawInRect:rect withAttributes:attributes];
}

static void DrawRoundedRect(NSRect rect, CGFloat radius, NSColor *fill, NSColor *stroke, CGFloat lineWidth) {
    NSBezierPath *path = [NSBezierPath bezierPathWithRoundedRect:rect xRadius:radius yRadius:radius];
    [fill setFill];
    [path fill];
    if (stroke && lineWidth > 0) {
        [stroke setStroke];
        path.lineWidth = lineWidth;
        [path stroke];
    }
}

static NSString *Reveal(NSString *text, CGFloat fraction) {
    if (fraction <= 0) return @"";
    if (fraction >= 1) return text;
    NSUInteger count = (NSUInteger)floor(text.length * fraction);
    return [text substringToIndex:count];
}

static NSInteger CapturedCommandExit(NSDictionary *evidence) {
    NSArray *events = evidence[@"unprotected"][@"trace"][@"stdout_events"];
    NSInteger result = -1;
    for (NSDictionary *record in events) {
        if ([record[@"item_type"] isEqual:@"command_execution"] && [record[@"exit_code"] isKindOfClass:[NSNumber class]]) {
            result = [record[@"exit_code"] integerValue];
        }
    }
    return result;
}

static NSInteger CommandExecutionCount(NSDictionary *profile) {
    NSInteger count = 0;
    for (NSDictionary *record in profile[@"trace"][@"stdout_events"]) {
        if ([record[@"item_type"] isEqual:@"command_execution"]) count++;
    }
    return count;
}

static void DrawTerminalChrome(NSRect panel, NSString *title, NSColor *accent, CGFloat textSize) {
    NSColor *panelFill = [NSColor colorWithCalibratedRed:0.055 green:0.071 blue:0.105 alpha:1];
    NSColor *panelLine = [NSColor colorWithCalibratedRed:0.18 green:0.23 blue:0.32 alpha:1];
    NSColor *barFill = [NSColor colorWithCalibratedRed:0.085 green:0.105 blue:0.145 alpha:1];
    NSColor *muted = [NSColor colorWithCalibratedRed:0.66 green:0.71 blue:0.79 alpha:1];
    DrawRoundedRect(panel, 15, panelFill, panelLine, 1.5);
    NSRect bar = NSMakeRect(panel.origin.x, panel.origin.y, panel.size.width, 44);
    DrawRoundedRect(bar, 15, barFill, nil, 0);
    [[NSColor colorWithCalibratedRed:1 green:0.38 blue:0.37 alpha:1] setFill];
    [[NSBezierPath bezierPathWithOvalInRect:NSMakeRect(panel.origin.x + 16, panel.origin.y + 17, 10, 10)] fill];
    [[NSColor colorWithCalibratedRed:1 green:0.76 blue:0.28 alpha:1] setFill];
    [[NSBezierPath bezierPathWithOvalInRect:NSMakeRect(panel.origin.x + 33, panel.origin.y + 17, 10, 10)] fill];
    [accent setFill];
    [[NSBezierPath bezierPathWithOvalInRect:NSMakeRect(panel.origin.x + 50, panel.origin.y + 17, 10, 10)] fill];
    DrawText(title, NSMakeRect(panel.origin.x + 74, panel.origin.y + 9, panel.size.width - 90, 28), textSize, muted, NSFontWeightSemibold, NSTextAlignmentLeft);
}

static void DrawFlow(NSRect rect, BOOL stopped, CGFloat size) {
    NSColor *white = [NSColor colorWithCalibratedRed:0.94 green:0.96 blue:1 alpha:1];
    NSColor *muted = [NSColor colorWithCalibratedRed:0.55 green:0.62 blue:0.72 alpha:1];
    NSColor *green = [NSColor colorWithCalibratedRed:0.32 green:0.90 blue:0.62 alpha:1];
    NSColor *red = [NSColor colorWithCalibratedRed:1 green:0.39 blue:0.39 alpha:1];
    CGFloat gap = 34;
    CGFloat boxWidth = (rect.size.width - 2 * gap) / 3;
    NSArray<NSString *> *labels = @[@"Agent", @"PreToolUse\nguard", @"Shell"];
    for (NSInteger index = 0; index < 3; index++) {
        NSRect box = NSMakeRect(rect.origin.x + index * (boxWidth + gap), rect.origin.y, boxWidth, rect.size.height);
        NSColor *line = index == 1 ? green : muted;
        DrawRoundedRect(box, 9, [NSColor colorWithCalibratedRed:0.075 green:0.095 blue:0.13 alpha:1], line, 1.5);
        DrawText(labels[index], NSInsetRect(box, 5, 8), size, index == 1 ? green : white, NSFontWeightSemibold, NSTextAlignmentCenter);
    }
    DrawText(@"→", NSMakeRect(rect.origin.x + boxWidth, rect.origin.y + 10, gap, rect.size.height - 10), size + 6, green, NSFontWeightBold, NSTextAlignmentCenter);
    DrawText(stopped ? @"×" : @"→", NSMakeRect(rect.origin.x + 2 * boxWidth + gap, rect.origin.y + 10, gap, rect.size.height - 10), size + 8, stopped ? red : muted, NSFontWeightBold, NSTextAlignmentCenter);
}

static void DrawCard(CGContextRef context, NSInteger width, NSInteger height, int second, NSDictionary *evidence) {
    CGContextSetRGBFillColor(context, 0.025, 0.034, 0.052, 1.0);
    CGContextFillRect(context, CGRectMake(0, 0, width, height));
    BOOL vertical = height > width;
    CGFloat margin = vertical ? 30 : 38;
    CGFloat headerHeight = vertical ? 104 : 82;
    CGFloat footerHeight = vertical ? 112 : 82;
    CGFloat gap = vertical ? 18 : 24;
    NSColor *white = [NSColor colorWithCalibratedRed:0.94 green:0.96 blue:1 alpha:1];
    NSColor *muted = [NSColor colorWithCalibratedRed:0.64 green:0.70 blue:0.80 alpha:1];
    NSColor *green = [NSColor colorWithCalibratedRed:0.30 green:0.88 blue:0.59 alpha:1];
    NSColor *red = [NSColor colorWithCalibratedRed:1.0 green:0.42 blue:0.42 alpha:1];
    NSString *command = evidence[@"command"];
    NSString *output = [evidence[@"unprotected"][@"command_output"] stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    NSString *reason = evidence[@"protected"][@"denial_reason"];
    NSString *version = evidence[@"tool"][@"codex_version"];
    NSInteger exitCode = CapturedCommandExit(evidence);
    NSInteger protectedExecutions = CommandExecutionCount(evidence[@"protected"]);

    DrawText(@"VERIFIED CAPTURE REPLAY", NSMakeRect(margin, 22, width - 2 * margin, 28), vertical ? 18 : 17, green, NSFontWeightBold, NSTextAlignmentLeft);
    DrawText(@"Same harmless command. Different boundary.", NSMakeRect(margin, vertical ? 52 : 48, width - 2 * margin, 38), vertical ? 25 : 30, white, NSFontWeightSemibold, NSTextAlignmentLeft);
    DrawText(version, NSMakeRect(margin, 24, width - 2 * margin, 24), vertical ? 15 : 16, muted, NSFontWeightRegular, NSTextAlignmentRight);

    NSRect leftPanel;
    NSRect rightPanel;
    CGFloat panelTop = margin + headerHeight;
    if (vertical) {
        CGFloat panelHeight = (height - panelTop - footerHeight - margin - gap) / 2;
        leftPanel = NSMakeRect(margin, panelTop, width - 2 * margin, panelHeight);
        rightPanel = NSMakeRect(margin, panelTop + panelHeight + gap, width - 2 * margin, panelHeight);
    } else {
        CGFloat panelWidth = (width - 2 * margin - gap) / 2;
        CGFloat panelHeight = height - panelTop - footerHeight - margin;
        leftPanel = NSMakeRect(margin, panelTop, panelWidth, panelHeight);
        rightPanel = NSMakeRect(margin + panelWidth + gap, panelTop, panelWidth, panelHeight);
    }

    CGFloat titleSize = vertical ? 18 : 17;
    CGFloat terminalSize = vertical ? 17 : 16;
    DrawTerminalChrome(leftPanel, @"Without the guard", red, titleSize);
    DrawTerminalChrome(rightPanel, @"With the guard", green, titleSize);

    CGFloat reveal = MIN(1.0, (second + 1) / 4.0);
    NSString *visibleCommand = Reveal(command, reveal);
    CGFloat inset = vertical ? 22 : 20;
    NSRect leftBody = NSInsetRect(NSMakeRect(leftPanel.origin.x, leftPanel.origin.y + 44, leftPanel.size.width, leftPanel.size.height - 44), inset, 16);
    NSRect rightBody = NSInsetRect(NSMakeRect(rightPanel.origin.x, rightPanel.origin.y + 44, rightPanel.size.width, rightPanel.size.height - 44), inset, 16);
    DrawText([NSString stringWithFormat:@"$ %@%@", visibleCommand, reveal < 1 ? @"▌" : @""], NSMakeRect(leftBody.origin.x, leftBody.origin.y, leftBody.size.width, 58), terminalSize, white, NSFontWeightRegular, NSTextAlignmentLeft);
    DrawText([NSString stringWithFormat:@"$ %@%@", visibleCommand, reveal < 1 ? @"▌" : @""], NSMakeRect(rightBody.origin.x, rightBody.origin.y, rightBody.size.width, 58), terminalSize, white, NSFontWeightRegular, NSTextAlignmentLeft);

    if (second >= 4) {
        NSString *leftText = second < 6 ? @"GUARD_INACTIVE_PROOF" : output;
        DrawText(leftText, NSMakeRect(leftBody.origin.x, leftBody.origin.y + 72, leftBody.size.width, vertical ? 100 : 120), terminalSize, second < 6 ? green : white, NSFontWeightRegular, NSTextAlignmentLeft);
    }
    if (second >= 7) {
        NSString *exitText = [NSString stringWithFormat:@"shell exit  %ld", (long)exitCode];
        DrawRoundedRect(NSMakeRect(leftBody.origin.x, NSMaxY(leftBody) - 42, 160, 30), 7, [NSColor colorWithCalibratedRed:0.22 green:0.08 blue:0.09 alpha:1], red, 1);
        DrawText(exitText, NSMakeRect(leftBody.origin.x + 8, NSMaxY(leftBody) - 37, 145, 22), terminalSize * 0.82, red, NSFontWeightBold, NSTextAlignmentLeft);
    }

    if (second >= 9) {
        DrawFlow(NSMakeRect(rightBody.origin.x, rightBody.origin.y + 70, rightBody.size.width, vertical ? 70 : 66), second >= 13, terminalSize * 0.82);
    }
    if (second >= 13) {
        DrawRoundedRect(NSMakeRect(rightBody.origin.x, rightBody.origin.y + 150, rightBody.size.width, 32), 7, [NSColor colorWithCalibratedRed:0.06 green:0.18 blue:0.13 alpha:1], green, 1);
        DrawText(@"BLOCKED BEFORE THE SHELL", NSMakeRect(rightBody.origin.x + 8, rightBody.origin.y + 155, rightBody.size.width - 16, 22), terminalSize * 0.78, green, NSFontWeightBold, NSTextAlignmentCenter);
    }
    if (second >= 16) {
        DrawText(reason, NSMakeRect(rightBody.origin.x, rightBody.origin.y + 196, rightBody.size.width, vertical ? 70 : 76), terminalSize * 0.88, white, NSFontWeightRegular, NSTextAlignmentLeft);
    }
    if (second >= 20) {
        NSString *facts = [NSString stringWithFormat:@"command_execution events  %ld\nmarker output              absent", (long)protectedExecutions];
        DrawText(facts, NSMakeRect(rightBody.origin.x, NSMaxY(rightBody) - (vertical ? 70 : 64), rightBody.size.width, 58), terminalSize * 0.78, muted, NSFontWeightRegular, NSTextAlignmentLeft);
    }

    NSRect footer = NSMakeRect(margin, height - footerHeight + 10, width - 2 * margin, footerHeight - 20);
    if (second >= 25) {
        DrawRoundedRect(footer, 10, [NSColor colorWithCalibratedRed:0.055 green:0.14 blue:0.11 alpha:1], green, 1);
        DrawText(@"Skills are the Instruction Layer. Hooks and guards are the Enforcement Layer.", NSInsetRect(footer, 14, 8), vertical ? 22 : 21, white, NSFontWeightSemibold, NSTextAlignmentCenter);
    } else {
        DrawText(@"Replay from the verified public capture. Not a live screen recording.", footer, vertical ? 17 : 16, muted, NSFontWeightRegular, NSTextAlignmentCenter);
    }
}

static CVPixelBufferRef MakePixelBuffer(NSInteger width, NSInteger height, int second, NSDictionary *evidence) {
    NSDictionary *attributes = @{
        (NSString *)kCVPixelBufferCGImageCompatibilityKey: @YES,
        (NSString *)kCVPixelBufferCGBitmapContextCompatibilityKey: @YES,
    };
    CVPixelBufferRef buffer = NULL;
    CVReturn result = CVPixelBufferCreate(kCFAllocatorDefault, width, height, kCVPixelFormatType_32BGRA, (__bridge CFDictionaryRef)attributes, &buffer);
    if (result != kCVReturnSuccess || !buffer) {
        return NULL;
    }
    CVPixelBufferLockBaseAddress(buffer, 0);
    void *base = CVPixelBufferGetBaseAddress(buffer);
    size_t rowBytes = CVPixelBufferGetBytesPerRow(buffer);
    CGColorSpaceRef colorSpace = CGColorSpaceCreateDeviceRGB();
    CGContextRef context = CGBitmapContextCreate(base, width, height, 8, rowBytes, colorSpace, kCGImageAlphaNoneSkipFirst | kCGBitmapByteOrder32Little);
    CGColorSpaceRelease(colorSpace);
    CGContextTranslateCTM(context, 0, height);
    CGContextScaleCTM(context, 1, -1);
    NSGraphicsContext *graphics = [NSGraphicsContext graphicsContextWithCGContext:context flipped:YES];
    [NSGraphicsContext saveGraphicsState];
    [NSGraphicsContext setCurrentContext:graphics];
    DrawCard(context, width, height, second, evidence);
    [NSGraphicsContext restoreGraphicsState];
    CGContextRelease(context);
    CVPixelBufferUnlockBaseAddress(buffer, 0);
    return buffer;
}

static BOOL RenderVideo(NSString *path, NSInteger width, NSInteger height, NSDictionary *evidence, NSString **outSemanticHash, NSError **outError) {
    [[NSFileManager defaultManager] removeItemAtPath:path error:nil];
    AVAssetWriter *writer = [[AVAssetWriter alloc] initWithURL:[NSURL fileURLWithPath:path] fileType:AVFileTypeMPEG4 error:outError];
    if (!writer) return NO;
    NSDictionary *compression = @{
        AVVideoAverageBitRateKey: @(width * height * 3),
        AVVideoMaxKeyFrameIntervalKey: @(kFPS),
        AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
    };
    NSDictionary *settings = @{
        AVVideoCodecKey: AVVideoCodecTypeH264,
        AVVideoWidthKey: @(width),
        AVVideoHeightKey: @(height),
        AVVideoCompressionPropertiesKey: compression,
    };
    AVAssetWriterInput *input = [AVAssetWriterInput assetWriterInputWithMediaType:AVMediaTypeVideo outputSettings:settings];
    input.expectsMediaDataInRealTime = NO;
    AVAssetWriterInputPixelBufferAdaptor *adaptor = [AVAssetWriterInputPixelBufferAdaptor assetWriterInputPixelBufferAdaptorWithAssetWriterInput:input sourcePixelBufferAttributes:@{
        (NSString *)kCVPixelBufferPixelFormatTypeKey: @(kCVPixelFormatType_32BGRA),
        (NSString *)kCVPixelBufferWidthKey: @(width),
        (NSString *)kCVPixelBufferHeightKey: @(height),
    }];
    if (![writer canAddInput:input]) return NO;
    [writer addInput:input];
    [writer startWriting];
    [writer startSessionAtSourceTime:kCMTimeZero];
    uint64_t semanticHash = UINT64_C(14695981039346656037);
    for (int frame = 0; frame < kDurationSeconds * kFPS; frame++) {
        while (!input.readyForMoreMediaData) {
            [NSThread sleepForTimeInterval:0.002];
        }
        int second = frame / kFPS;
        CVPixelBufferRef buffer = MakePixelBuffer(width, height, second, evidence);
        if (!buffer) return NO;
        CVPixelBufferLockBaseAddress(buffer, kCVPixelBufferLock_ReadOnly);
        const uint8_t *base = CVPixelBufferGetBaseAddress(buffer);
        size_t rowBytes = CVPixelBufferGetBytesPerRow(buffer);
        for (NSInteger row = 0; row < height; row++) {
            semanticHash = UpdateFNV1a64(semanticHash, base + row * rowBytes, (size_t)width * 4);
        }
        CVPixelBufferUnlockBaseAddress(buffer, kCVPixelBufferLock_ReadOnly);
        BOOL appended = [adaptor appendPixelBuffer:buffer withPresentationTime:CMTimeMake(frame, kFPS)];
        CVPixelBufferRelease(buffer);
        if (!appended) return NO;
    }
    [input markAsFinished];
    dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);
    [writer finishWritingWithCompletionHandler:^{ dispatch_semaphore_signal(semaphore); }];
    dispatch_semaphore_wait(semaphore, DISPATCH_TIME_FOREVER);
    if (writer.status != AVAssetWriterStatusCompleted) {
        if (outError) *outError = writer.error;
        return NO;
    }
    if (outSemanticHash) *outSemanticHash = FNV1a64String(semanticHash);
    return YES;
}

static NSDictionary *InspectVideo(NSString *path, NSError **outError) {
    AVURLAsset *asset = [AVURLAsset URLAssetWithURL:[NSURL fileURLWithPath:path] options:nil];
    NSArray<AVAssetTrack *> *videoTracks = [asset tracksWithMediaType:AVMediaTypeVideo];
    NSArray<AVAssetTrack *> *audioTracks = [asset tracksWithMediaType:AVMediaTypeAudio];
    if (videoTracks.count != 1) {
        if (outError) {
            *outError = [NSError errorWithDomain:@"GuardRenderer" code:1 userInfo:@{NSLocalizedDescriptionKey: @"rendered asset must have exactly one video track"}];
        }
        return nil;
    }
    if (audioTracks.count != 0) {
        if (outError) {
            *outError = [NSError errorWithDomain:@"GuardRenderer" code:2 userInfo:@{NSLocalizedDescriptionKey: @"rendered asset must not contain an audio track"}];
        }
        return nil;
    }
    AVAssetTrack *track = videoTracks.firstObject;
    CGSize transformed = CGSizeApplyAffineTransform(track.naturalSize, track.preferredTransform);
    return @{
        @"width": @((NSInteger)llround(fabs(transformed.width))),
        @"height": @((NSInteger)llround(fabs(transformed.height))),
        @"duration_seconds": @((NSInteger)llround(CMTimeGetSeconds(asset.duration))),
        @"frame_rate": @((NSInteger)llround(track.nominalFrameRate)),
        @"audio_tracks": @(audioTracks.count),
        @"video_tracks": @(videoTracks.count),
    };
}

static BOOL RenderPoster(NSString *path, NSDictionary *evidence) {
    NSInteger width = 1280, height = 720;
    NSBitmapImageRep *bitmap = [[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:width pixelsHigh:height bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSCalibratedRGBColorSpace bytesPerRow:0 bitsPerPixel:0];
    NSGraphicsContext *bitmapGraphics = [NSGraphicsContext graphicsContextWithBitmapImageRep:bitmap];
    CGContextRef context = bitmapGraphics.CGContext;
    CGContextTranslateCTM(context, 0, height);
    CGContextScaleCTM(context, 1, -1);
    NSGraphicsContext *graphics = [NSGraphicsContext graphicsContextWithCGContext:context flipped:YES];
    [NSGraphicsContext saveGraphicsState];
    [NSGraphicsContext setCurrentContext:graphics];
    DrawCard(context, width, height, 26, evidence);
    [NSGraphicsContext restoreGraphicsState];
    NSData *png = [bitmap representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
    return [png writeToFile:path atomically:YES];
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 6) {
            fprintf(stderr, "usage: render_media EVIDENCE WIDE VERTICAL POSTER METADATA\n");
            return 2;
        }
        NSDictionary *evidence = ReadEvidence(@(argv[1]));
        NSError *error = nil;
        NSString *wideSemanticHash = nil;
        NSString *verticalSemanticHash = nil;
        if (!RenderVideo(@(argv[2]), 1280, 720, evidence, &wideSemanticHash, &error)) {
            fprintf(stderr, "wide render failed: %s\n", error.localizedDescription.UTF8String);
            return 1;
        }
        error = nil;
        if (!RenderVideo(@(argv[3]), 720, 1280, evidence, &verticalSemanticHash, &error)) {
            fprintf(stderr, "vertical render failed: %s\n", error.localizedDescription.UTF8String);
            return 1;
        }
        if (!RenderPoster(@(argv[4]), evidence)) {
            fprintf(stderr, "poster render failed\n");
            return 1;
        }
        NSMutableDictionary *wide = [InspectVideo(@(argv[2]), &error) mutableCopy];
        if (!wide) {
            fprintf(stderr, "wide inspection failed: %s\n", error.localizedDescription.UTF8String);
            return 1;
        }
        wide[@"semantic_frame_hash"] = wideSemanticHash;
        error = nil;
        NSMutableDictionary *vertical = [InspectVideo(@(argv[3]), &error) mutableCopy];
        if (!vertical) {
            fprintf(stderr, "vertical inspection failed: %s\n", error.localizedDescription.UTF8String);
            return 1;
        }
        vertical[@"semantic_frame_hash"] = verticalSemanticHash;
        NSDictionary *metadata = @{
            @"codec": @"H.264 High Auto Level",
            @"wide": wide,
            @"vertical": vertical,
        };
        NSData *data = [NSJSONSerialization dataWithJSONObject:metadata options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:&error];
        if (!data || ![data writeToFile:@(argv[5]) options:NSDataWritingAtomic error:&error]) {
            fprintf(stderr, "metadata write failed: %s\n", error.localizedDescription.UTF8String);
            return 1;
        }
    }
    return 0;
}
