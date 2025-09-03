if (navigator.userAgentData) {
  navigator.userAgentData.getHighEntropyValues(['userAgent']).then((uaData) => {
    const userAgent = uaData.userAgent;
    // Use the retrieved user agent string as needed
  }).catch((error) => {
    // Handle any errors that occur during retrieval
  });
} else {
  // Fallback for browsers that do not support navigator.userAgentData
  const userAgent = navigator.userAgent;
  // Use the userAgent string as needed
}
// JavaScript Document