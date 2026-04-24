import { Request, Response, NextFunction } from 'express';
import { v4 as uuidv4 } from 'uuid';

/**
 * Extends the Express Request interface to include a reqId
 */
declare global {
  namespace Express {
    interface Request {
      reqId: string;
    }
  }
}

/**
 * Middleware to assign a unique request ID to each incoming request
 */
export function requestIdMiddleware(req: Request, res: Response, next: NextFunction) {
  req.reqId = (req.headers['x-request-id'] as string) || uuidv4();
  res.setHeader('X-Request-Id', req.reqId);
  next();
}

/**
 * Basic structured logger that includes timestamps, log levels, and request IDs (if available)
 */
export const logger = {
  info: (msg: string, meta: Record<string, any> = {}) => log('INFO', msg, meta),
  warn: (msg: string, meta: Record<string, any> = {}) => log('WARN', msg, meta),
  error: (msg: string, meta: Record<string, any> = {}) => log('ERROR', msg, meta),
  debug: (msg: string, meta: Record<string, any> = {}) => log('DEBUG', msg, meta),
};

function log(level: string, msg: string, meta: Record<string, any>) {
  const timestamp = new Date().toISOString();
  
  let formattedMeta = '';
  if (Object.keys(meta).length > 0) {
      if (meta instanceof Error) {
          formattedMeta = ` | error: ${meta.message}`;
          if (meta.stack) {
              formattedMeta += `\n${meta.stack}`;
          }
      } else {
         try {
             formattedMeta = ` | ${JSON.stringify(meta)}`;
         } catch {
             formattedMeta = ' | [Circular object]';
         }
      }
  }

  const reqIdStr = meta.reqId ? `[${meta.reqId}] ` : '';
  
  if (level === 'ERROR') {
      console.error(`[${timestamp}] ${level} - ${reqIdStr}${msg}${formattedMeta}`);
  } else if (level === 'WARN') {
      console.warn(`[${timestamp}] ${level} - ${reqIdStr}${msg}${formattedMeta}`);
  } else {
      console.log(`[${timestamp}] ${level} - ${reqIdStr}${msg}${formattedMeta}`);
  }
}

/**
 * Middleware to log incoming requests and their response times
 */
export function requestLoggerMiddleware(req: Request, res: Response, next: NextFunction) {
  const start = Date.now();
  
  res.on('finish', () => {
    const duration = Date.now() - start;
    logger.info(`${req.method} ${req.originalUrl} - ${res.statusCode} [${duration}ms]`, {
      reqId: req.reqId,
      ip: req.ip,
      userAgent: req.headers['user-agent']
    });
  });
  
  next();
}
